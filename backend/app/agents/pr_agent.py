"""
PR Review Agent — AI-powered pull request analysis.

Design — parallel focused calls, one assembly step
───────────────────────────────────────────────────
A PR analysis needs four distinct kinds of output:
  1. Code Review     — line-level quality assessment (bugs, style, best practices)
  2. Change Summary  — plain-English explanation of what changed and why
  3. Optimization    — concrete suggestions to improve the diff
  4. Impact Analysis — which other files/functions are affected (Neo4j-driven)

Each of these benefits from a different framing and reads different context,
so they run as separate parallel LLM calls (asyncio.gather) — same pattern as
the documentation agent. A final lightweight call synthesizes them into a
single decision + confidence score, since that judgment needs to see all four
outputs together.

Total calls per PR analysis: 4 parallel + 1 synthesis = 5 LLM calls.
Wall-clock time: roughly the same as 2 sequential calls (~15-20s).

Model: google/gemini-flash-1.5  (same as doc agent — PR review needs strong
       reasoning, and this runs on-demand per PR, not interactively)
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from loguru import logger
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.github_service import PRDetail, PRFileChange
from app.services.graph_store import get_file_impact

settings = get_settings()

PR_MODEL    = "google/gemini-2.5-flash"
MAX_TOKENS  = 2500
TEMPERATURE = 0.2

MAX_DIFF_CHARS_PER_FILE = 3000   # truncate huge diffs to control token cost
MAX_FILES_IN_PROMPT     = 20     # cap files sent to LLM (impact analysis covers the rest via graph)


def _llm() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key  = settings.openrouter_api_key,
        base_url = settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://codenavigator.dev",
            "X-Title":      "CodeNavigator",
        },
    )


# ── Diff formatting ────────────────────────────────────────────────────────────

def _format_diff_for_prompt(files: list[PRFileChange]) -> str:
    """Render the PR's file diffs as a single Markdown block for the LLM."""
    parts: list[str] = []
    for f in files[:MAX_FILES_IN_PROMPT]:
        header = f"### `{f.filename}` ({f.status}, +{f.additions}/-{f.deletions})"
        if f.previous_filename:
            header += f" — renamed from `{f.previous_filename}`"

        if f.patch is None:
            parts.append(f"{header}\n_Binary file — no diff available._")
            continue

        patch = f.patch
        if len(patch) > MAX_DIFF_CHARS_PER_FILE:
            patch = patch[:MAX_DIFF_CHARS_PER_FILE] + "\n... (diff truncated for length) ..."

        parts.append(f"{header}\n```diff\n{patch}\n```")

    if len(files) > MAX_FILES_IN_PROMPT:
        remaining = len(files) - MAX_FILES_IN_PROMPT
        parts.append(f"\n_...and {remaining} more file(s) not shown (see impact analysis for full file list)._")

    return "\n\n".join(parts)


def _pr_header(pr: PRDetail) -> str:
    return (
        f"**PR #{pr.number}: {pr.title}**\n"
        f"Author: {pr.author} | {pr.base_branch} ← {pr.head_branch}\n"
        f"{pr.files_changed} files changed, +{pr.additions}/-{pr.deletions}, {pr.commits} commit(s)\n\n"
        f"**Description:**\n{pr.body or '_No description provided._'}"
    )


# ── 1. Code Review ──────────────────────────────────────────────────────────────

_CODE_REVIEW_PROMPT = """You are a senior software engineer performing a thorough code review.

Review the diff for:
- **Bugs**: logic errors, null/undefined handling, off-by-one errors, race conditions
- **Security**: injection risks, secret exposure, unsafe deserialisation, missing auth checks
- **Performance**: N+1 queries, unnecessary loops, missing indexes, blocking calls in async code
- **Maintainability**: code duplication, naming, complexity, missing error handling
- **Best practices**: idiomatic usage for the language/framework, test coverage gaps

Output format
──────────────
For each file with notable findings, use:
  #### `filename`
  - 🔴 **Bug**: description (line reference if visible in the diff)
  - 🟡 **Suggestion**: description
  - 🟢 **Good**: something done well (include at least one per review if applicable)

End with a one-paragraph overall assessment.
If the diff is clean with no significant issues, say so explicitly — do not invent problems.
Use Markdown. Be specific and reference actual code from the diff."""


async def _run_code_review(pr: PRDetail, diff_text: str) -> tuple[str, int]:
    messages = [
        {"role": "system", "content": _CODE_REVIEW_PROMPT},
        {"role": "user", "content": f"{_pr_header(pr)}\n\n**Diff:**\n\n{diff_text}"},
    ]
    resp = await _llm().chat.completions.create(
        model=PR_MODEL, messages=messages, max_tokens=MAX_TOKENS, temperature=TEMPERATURE,
    )
    content = resp.choices[0].message.content or ""
    tokens  = resp.usage.total_tokens if resp.usage else 0
    return content.strip(), tokens


# ── 2. Change Summary ───────────────────────────────────────────────────────────

_SUMMARY_PROMPT = """You are a technical writer explaining a pull request to a non-author teammate.

Write a clear, plain-English summary covering:
- **What changed**: the concrete code/behaviour changes (2-4 sentences)
- **Why** (inferred from the PR description, commit context, and the diff itself)
- **Scope**: which areas of the codebase this touches (auth, API, database, UI, etc.)

Keep it to 1-2 short paragraphs. Avoid restating the diff line-by-line — synthesise it.
Use Markdown, no headers needed for this short summary."""


async def _run_summary(pr: PRDetail, diff_text: str) -> tuple[str, int]:
    messages = [
        {"role": "system", "content": _SUMMARY_PROMPT},
        {"role": "user", "content": f"{_pr_header(pr)}\n\n**Diff:**\n\n{diff_text}"},
    ]
    resp = await _llm().chat.completions.create(
        model=PR_MODEL, messages=messages, max_tokens=600, temperature=TEMPERATURE,
    )
    content = resp.choices[0].message.content or ""
    tokens  = resp.usage.total_tokens if resp.usage else 0
    return content.strip(), tokens


# ── 3. Optimization Suggestions ────────────────────────────────────────────────

_OPTIMIZATION_PROMPT = """You are a principal engineer suggesting concrete improvements to a pull request's diff.

For each suggestion:
- Reference the specific file and approximate location
- Show a brief "before → after" code snippet where useful (keep snippets short, <10 lines)
- Explain the benefit (performance, readability, safety, maintainability)

Prioritise suggestions that matter — skip purely stylistic nits unless nothing else is found.
If the diff is already well-optimised, say so explicitly and skip fabricating suggestions.
Limit to the 5 most impactful suggestions. Use Markdown with `#### File: suggestion title` headers."""


async def _run_optimization(pr: PRDetail, diff_text: str) -> tuple[str, int]:
    messages = [
        {"role": "system", "content": _OPTIMIZATION_PROMPT},
        {"role": "user", "content": f"{_pr_header(pr)}\n\n**Diff:**\n\n{diff_text}"},
    ]
    resp = await _llm().chat.completions.create(
        model=PR_MODEL, messages=messages, max_tokens=1800, temperature=TEMPERATURE,
    )
    content = resp.choices[0].message.content or ""
    tokens  = resp.usage.total_tokens if resp.usage else 0
    return content.strip(), tokens


# ── 4. Impact Analysis (Neo4j-driven) ──────────────────────────────────────────

async def _run_impact_analysis(
    repo_id: str,
    files: list[PRFileChange],
) -> dict:
    """
    For every changed file, query Neo4j for what depends on it.
    Returns a structured dict — no LLM call needed, pure graph traversal.
    Runs all file lookups in parallel.
    """
    changed_paths = [f.filename for f in files if f.status != "added"]  # new files have no existing dependents

    if not changed_paths:
        return {"per_file": {}, "total_dependent_files": 0, "total_affected_functions": 0, "breaking_change_risk": "low"}

    tasks = [get_file_impact(repo_id, path) for path in changed_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    per_file: dict[str, dict] = {}
    total_dependents  = 0
    total_callers      = 0
    has_subclass_risk  = False

    for path, result in zip(changed_paths, results):
        if isinstance(result, Exception):
            logger.debug(f"Impact lookup failed for {path} (non-fatal): {result}")
            continue
        per_file[path] = result
        total_dependents += len(result.get("dependent_files", []))
        total_callers     += len(result.get("callers_of_functions", []))
        if result.get("subclasses"):
            has_subclass_risk = True

    # Heuristic risk level
    if has_subclass_risk or total_callers > 10:
        risk = "high"
    elif total_dependents > 3 or total_callers > 3:
        risk = "medium"
    else:
        risk = "low"

    return {
        "per_file":                 per_file,
        "total_dependent_files":    total_dependents,
        "total_affected_functions": total_callers,
        "breaking_change_risk":     risk,
    }


def _format_impact_for_prompt(impact: dict) -> str:
    """Render impact analysis as Markdown for the synthesis call."""
    if not impact.get("per_file"):
        return "No cross-file dependencies found (or all changed files are newly added)."

    lines = [
        f"**Risk level**: {impact['breaking_change_risk']} "
        f"({impact['total_dependent_files']} dependent files, "
        f"{impact['total_affected_functions']} affected call sites)"
    ]
    for path, data in impact["per_file"].items():
        if not any(data.values()):
            continue
        lines.append(f"\n**`{path}`**:")
        if data.get("dependent_files"):
            deps = ", ".join(f"`{d['file_path']}`" for d in data["dependent_files"][:5])
            lines.append(f"  - Imported by: {deps}")
        if data.get("callers_of_functions"):
            callers = ", ".join(
                f"`{c['caller']}()` in `{c['caller_file']}`" for c in data["callers_of_functions"][:5]
            )
            lines.append(f"  - Functions called from: {callers}")
        if data.get("subclasses"):
            subs = ", ".join(f"`{s['subclass']}` extends `{s['class']}`" for s in data["subclasses"][:5])
            lines.append(f"  - ⚠️ Subclasses that may break: {subs}")
    return "\n".join(lines)


# ── 5. Synthesis: decision + confidence ────────────────────────────────────────

_SYNTHESIS_PROMPT = """You are a senior engineering lead making the final call on a pull request.

You have been given:
  - A code review (bugs, security, performance, maintainability findings)
  - A plain-English summary of the change
  - Optimization suggestions
  - An impact analysis showing what else in the codebase depends on the changed files

Make a decision: APPROVE, REQUEST_CHANGES, or REJECT.

Guidelines:
- APPROVE: no significant issues, low/medium risk, change is sound
- REQUEST_CHANGES: fixable issues found (bugs, missing tests, style) but the approach is reasonable
- REJECT: severe issues (security vulnerability, fundamentally broken approach, high breaking-change risk with no mitigation)

Output EXACTLY in this format (no extra text before or after):

DECISION: <APPROVE|REQUEST_CHANGES|REJECT>
CONFIDENCE: <a number between 0.0 and 1.0>
RISK_FLAGS: <comma-separated tags from: security, breaking_change, performance, untested, style_only, none>
REASON: <2-3 sentences explaining the decision, referencing the most important finding>"""


def _parse_synthesis(text: str) -> dict:
    """Parse the structured synthesis response into a dict. Tolerant of minor format drift."""
    decision   = "request_changes"
    confidence = 0.5
    risk_flags: list[str] = []
    reason     = text.strip()

    decision_match = re.search(r"DECISION:\s*(APPROVE|REQUEST_CHANGES|REJECT)", text, re.IGNORECASE)
    if decision_match:
        decision = decision_match.group(1).lower()

    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
    if conf_match:
        try:
            confidence = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            pass

    flags_match = re.search(r"RISK_FLAGS:\s*(.+)", text)
    if flags_match:
        raw_flags = flags_match.group(1).split("\n")[0]
        risk_flags = [f.strip() for f in raw_flags.split(",") if f.strip() and f.strip().lower() != "none"]

    reason_match = re.search(r"REASON:\s*(.+)", text, re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip()

    return {
        "decision":   decision,
        "confidence": confidence,
        "risk_flags": risk_flags,
        "reason":     reason,
    }


async def _run_synthesis(
    pr: PRDetail,
    code_review: str,
    summary: str,
    impact_text: str,
) -> tuple[dict, int]:
    user_content = (
        f"{_pr_header(pr)}\n\n"
        f"**Summary:**\n{summary}\n\n"
        f"**Code review findings:**\n{code_review}\n\n"
        f"**Impact analysis:**\n{impact_text}"
    )
    messages = [
        {"role": "system", "content": _SYNTHESIS_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    resp = await _llm().chat.completions.create(
        model=PR_MODEL, messages=messages, max_tokens=400, temperature=0.1,
    )
    content = resp.choices[0].message.content or ""
    tokens  = resp.usage.total_tokens if resp.usage else 0
    return _parse_synthesis(content), tokens


# ── Public entry point ─────────────────────────────────────────────────────────

@dataclass
class PRAnalysisResult:
    summary:                   str
    code_review:               str
    optimization_suggestions:  str
    impact_analysis:           dict
    decision:                  str       # "approve" | "request_changes" | "reject"
    confidence_score:           float
    risk_flags:                list[str]
    decision_reason:           str
    total_tokens:              int
    status:                    str = "done"   # "done" | "failed"
    error:                     str = ""


async def analyze_pull_request(
    pr: PRDetail,
    repo_id: str,
) -> PRAnalysisResult:
    """
    Full PR analysis pipeline.

    Stage 1 (parallel): code review · summary · optimization · impact analysis
    Stage 2 (sequential, needs Stage 1 outputs): synthesis → decision + confidence
    """
    diff_text = _format_diff_for_prompt(pr.files or [])

    try:
        # ── Stage 1: parallel ────────────────────────────────────────────────
        review_task   = _run_code_review(pr, diff_text)
        summary_task  = _run_summary(pr, diff_text)
        optim_task    = _run_optimization(pr, diff_text)
        impact_task   = _run_impact_analysis(repo_id, pr.files or [])

        (code_review, review_tokens), (summary, summary_tokens), \
            (optimization, optim_tokens), impact = await asyncio.gather(
                review_task, summary_task, optim_task, impact_task,
            )

        impact_text = _format_impact_for_prompt(impact)

        # ── Stage 2: synthesis (needs Stage 1 results) ──────────────────────
        synthesis, synthesis_tokens = await _run_synthesis(pr, code_review, summary, impact_text)

        total_tokens = review_tokens + summary_tokens + optim_tokens + synthesis_tokens

        return PRAnalysisResult(
            summary                  = summary,
            code_review              = code_review,
            optimization_suggestions = optimization,
            impact_analysis          = impact,
            decision                 = synthesis["decision"],
            confidence_score         = synthesis["confidence"],
            risk_flags               = synthesis["risk_flags"],
            decision_reason          = synthesis["reason"],
            total_tokens             = total_tokens,
            status                   = "done",
        )

    except Exception as exc:
        logger.exception(f"PR analysis failed for PR #{pr.number}: {exc}")
        return PRAnalysisResult(
            summary                  = "",
            code_review              = "",
            optimization_suggestions = "",
            impact_analysis          = {},
            decision                 = "request_changes",
            confidence_score         = 0.0,
            risk_flags               = [],
            decision_reason          = f"Analysis failed: {exc}",
            total_tokens             = 0,
            status                   = "failed",
            error                    = str(exc),
        )
