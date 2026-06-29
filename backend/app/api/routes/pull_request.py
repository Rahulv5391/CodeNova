"""
Pull Request routes — list, analyze, and decide on PRs for a repository.

Endpoints
─────────
GET    /prs/{repo_id}                          List all PRs (live from GitHub + cached AI status)
GET    /prs/{repo_id}/{pr_number}              Full PR detail with file diffs
POST   /prs/{repo_id}/{pr_number}/analyze      Run AI analysis (sync — waits ~15-20s)
GET    /prs/{repo_id}/{pr_number}/analyze/stream   Run AI analysis with SSE progress
GET    /prs/{repo_id}/{pr_number}/analysis     Retrieve cached analysis (no re-run)
POST   /prs/{repo_id}/{pr_number}/decision     Approve or reject (writes back to GitHub)

Design notes
────────────
PR listing always hits the live GitHub API (PRs change frequently — state, comments,
mergeable status). It's joined with our local PullRequestReview table to attach
cached AI decision + human decision, so the list view shows everything in one call.

Analysis results are cached in Postgres. Calling /analyze again with
force_reanalyze=false returns the same cached result instantly. This avoids
burning tokens on PRs that haven't changed.

The /decision endpoint requires the user's GitHub access token (stored at
login via OAuth) to have write access to the repo, since it posts a real
review and optionally merges/closes the PR on GitHub.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pr_agent import PRAnalysisResult, analyze_pull_request
from app.api.deps import get_current_user
from app.api.routes.repositories import _get_repo_or_404
from app.core.database import get_db
from app.models.models import PullRequestReview, Repository, User
from app.schemas.schemas import (
    ImpactAnalysisOut,
    PRAnalysisOut,
    PRAnalyzeRequest,
    PRDecisionRequest,
    PRDecisionResponse,
    PRDetailOut,
    PRFileOut,
    PRSummaryOut,
)
from app.services.github_service import (
    close_pull_request,
    get_pull_request,
    list_pull_requests,
    merge_pull_request,
    post_pr_review_comment,
)

router = APIRouter(prefix="/prs", tags=["pull-requests"])


# ════════════════════════════════════════════════════════════════════════════════
# List & detail (live from GitHub)
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{repo_id}",
    response_model=list[PRSummaryOut],
    summary="List pull requests for a repository",
)
async def list_prs(
    repo_id: uuid.UUID,
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List PRs for the repository, live from GitHub, enriched with cached AI
    analysis status and human decision from our database.

    **state**: "open" (default) | "closed" | "all"
    """
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    try:
        prs = list_pull_requests(
            github_url   = repo.github_url,
            access_token = repo.github_access_token or current_user.github_access_token,
            state        = state,
            limit        = limit,
        )
    except Exception as exc:
        logger.warning(f"Failed to list PRs for {repo.full_name}: {exc}")
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    # Fetch cached review rows for these PR numbers in one query
    pr_numbers = [pr.number for pr in prs]
    reviews_result = await db.execute(
        select(PullRequestReview).where(
            PullRequestReview.repository_id == repo_id,
            PullRequestReview.pr_number.in_(pr_numbers),
        )
    )
    reviews_by_number = {r.pr_number: r for r in reviews_result.scalars().all()}

    out: list[PRSummaryOut] = []
    for pr in prs:
        review = reviews_by_number.get(pr.number)
        out.append(PRSummaryOut(
            number          = pr.number,
            title           = pr.title,
            body            = pr.body,
            author          = pr.author,
            state           = pr.state,
            merged          = pr.merged,
            base_branch     = pr.base_branch,
            head_branch     = pr.head_branch,
            created_at      = pr.created_at,
            updated_at      = pr.updated_at,
            url             = pr.url,
            files_changed   = pr.files_changed,
            additions       = pr.additions,
            deletions       = pr.deletions,
            commits         = pr.commits,
            mergeable       = pr.mergeable,
            analysis_status = review.analysis_status if review else "not_analyzed",
            ai_decision     = review.ai_decision      if review else None,
            confidence_score= review.confidence_score if review else None,
            human_decision  = review.human_decision   if review else "pending",
        ))

    return out


@router.get(
    "/{repo_id}/{pr_number}",
    response_model=PRDetailOut,
    summary="Get full PR detail with file diffs",
)
async def get_pr_detail(
    repo_id: uuid.UUID,
    pr_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full PR detail including per-file unified diffs.
    Use this to render the PR diff view before triggering analysis.
    """
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    try:
        pr = get_pull_request(
            github_url   = repo.github_url,
            pr_number    = pr_number,
            access_token = repo.github_access_token or current_user.github_access_token,
        )
    except Exception as exc:
        logger.warning(f"Failed to fetch PR #{pr_number} for {repo.full_name}: {exc}")
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    review = await _get_review(repo_id, pr_number, db)

    return PRDetailOut(
        number          = pr.number,
        title           = pr.title,
        body            = pr.body,
        author          = pr.author,
        state           = pr.state,
        merged          = pr.merged,
        base_branch     = pr.base_branch,
        head_branch     = pr.head_branch,
        created_at      = pr.created_at,
        updated_at      = pr.updated_at,
        url             = pr.url,
        files_changed   = pr.files_changed,
        additions       = pr.additions,
        deletions       = pr.deletions,
        commits         = pr.commits,
        mergeable       = pr.mergeable,
        analysis_status = review.analysis_status if review else "not_analyzed",
        ai_decision     = review.ai_decision      if review else None,
        confidence_score= review.confidence_score if review else None,
        human_decision  = review.human_decision   if review else "pending",
        files           = [
            PRFileOut(
                filename=f.filename, status=f.status, additions=f.additions,
                deletions=f.deletions, changes=f.changes, patch=f.patch,
                previous_filename=f.previous_filename,
            )
            for f in (pr.files or [])
        ],
    )


# ════════════════════════════════════════════════════════════════════════════════
# AI Analysis — synchronous
# ════════════════════════════════════════════════════════════════════════════════

@router.post(
    "/{repo_id}/{pr_number}/analyze",
    response_model=PRAnalysisOut,
    summary="Run AI analysis on a PR (code review, impact, optimization, decision)",
)
async def analyze_pr(
    repo_id: uuid.UUID,
    pr_number: int,
    body: PRAnalyzeRequest = PRAnalyzeRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run full AI analysis on a pull request:

    1. **Code review** — bugs, security, performance, maintainability findings
    2. **Change summary** — plain-English explanation of what changed and why
    3. **Optimization suggestions** — concrete improvements with before/after snippets
    4. **Impact analysis** — Neo4j-driven: which files/functions depend on the changed code
    5. **Decision + confidence** — APPROVE / REQUEST_CHANGES / REJECT with a 0-1 confidence score

    Results are cached. Calling this again with `force_reanalyze=false` (default)
    returns the cached result instantly if one exists. Pass `force_reanalyze=true`
    to re-run (e.g. after the PR author pushes new commits).

    Typical latency: 15-25 seconds (4 parallel calls + 1 synthesis call).
    """
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    existing = await _get_review(repo_id, pr_number, db)
    if existing and existing.analysis_status == "done" and not body.force_reanalyze:
        return _review_to_out(existing)

    # Fetch PR detail (with diffs) from GitHub
    try:
        pr = get_pull_request(
            github_url   = repo.github_url,
            pr_number    = pr_number,
            access_token = repo.github_access_token or current_user.github_access_token,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    # Upsert review row → status = analyzing
    review = existing or PullRequestReview(
        repository_id = repo_id,
        owner_id      = current_user.id,
        pr_number     = pr_number,
    )
    review.pr_title        = pr.title
    review.pr_author       = pr.author
    review.pr_url          = pr.url
    review.base_branch     = pr.base_branch
    review.head_branch     = pr.head_branch
    review.files_changed   = pr.files_changed
    review.additions       = pr.additions
    review.deletions       = pr.deletions
    review.analysis_status = "analyzing"
    if not existing:
        db.add(review)
    await db.commit()
    await db.refresh(review)

    # Run the analysis
    result: PRAnalysisResult = await analyze_pull_request(pr, repo_id=str(repo_id))

    # Persist result
    review.summary                  = result.summary
    review.code_review              = result.code_review
    review.impact_analysis          = result.impact_analysis
    review.optimization_suggestions = result.optimization_suggestions
    review.risk_flags               = result.risk_flags
    review.confidence_score         = result.confidence_score
    review.ai_decision              = result.decision
    review.ai_decision_reason       = result.decision_reason
    review.total_tokens             = result.total_tokens
    review.analysis_status          = "done" if result.status == "done" else "failed"
    review.error_message            = result.error or None
    await db.commit()
    await db.refresh(review)

    return _review_to_out(review)


# ════════════════════════════════════════════════════════════════════════════════
# AI Analysis — SSE streaming progress
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{repo_id}/{pr_number}/analyze/stream",
    summary="Run AI analysis with live SSE progress events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def analyze_pr_stream(
    repo_id: uuid.UUID,
    pr_number: int,
    force_reanalyze: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Same analysis as POST .../analyze, but streams progress as each stage completes.

    SSE event sequence:
    ```
    data: {"type": "start",   "pr_number": 42}
    data: {"type": "stage",   "stage": "code_review",     "status": "running"}
    data: {"type": "stage",   "stage": "summary",         "status": "running"}
    data: {"type": "stage",   "stage": "optimization",    "status": "running"}
    data: {"type": "stage",   "stage": "impact_analysis", "status": "running"}
    data: {"type": "stage",   "stage": "synthesis",       "status": "running"}
    data: {"type": "done",    "analysis": { ...PRAnalysisOut... }}
    data: {"type": "error",   "message": "..."}
    ```

    Note: because the four Stage-1 calls run in parallel internally, the
    frontend will see all four "running" events fire close together, then
    a pause, then "synthesis", then "done" with the complete result.
    """
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    existing = await _get_review(repo_id, pr_number, db)

    async def event_stream():
        yield _sse({"type": "start", "pr_number": pr_number})

        if existing and existing.analysis_status == "done" and not force_reanalyze:
            yield _sse({"type": "done", "analysis": _review_to_out(existing).model_dump(mode="json")})
            return

        try:
            pr = get_pull_request(
                github_url   = repo.github_url,
                pr_number    = pr_number,
                access_token = repo.github_access_token or current_user.github_access_token,
            )
        except Exception as exc:
            yield _sse({"type": "error", "message": f"GitHub API error: {exc}"})
            return

        review = existing or PullRequestReview(
            repository_id=repo_id, owner_id=current_user.id, pr_number=pr_number,
        )
        review.pr_title, review.pr_author, review.pr_url = pr.title, pr.author, pr.url
        review.base_branch, review.head_branch = pr.base_branch, pr.head_branch
        review.files_changed, review.additions, review.deletions = pr.files_changed, pr.additions, pr.deletions
        review.analysis_status = "analyzing"
        if not existing:
            db.add(review)
        await db.commit()
        await db.refresh(review)

        for stage in ("code_review", "summary", "optimization", "impact_analysis"):
            yield _sse({"type": "stage", "stage": stage, "status": "running"})

        try:
            result = await analyze_pull_request(pr, repo_id=str(repo_id))
        except Exception as exc:
            review.analysis_status = "failed"
            review.error_message   = str(exc)
            await db.commit()
            yield _sse({"type": "error", "message": str(exc)})
            return

        yield _sse({"type": "stage", "stage": "synthesis", "status": "running"})

        review.summary                  = result.summary
        review.code_review              = result.code_review
        review.impact_analysis          = result.impact_analysis
        review.optimization_suggestions = result.optimization_suggestions
        review.risk_flags               = result.risk_flags
        review.confidence_score         = result.confidence_score
        review.ai_decision              = result.decision
        review.ai_decision_reason       = result.decision_reason
        review.total_tokens             = result.total_tokens
        review.analysis_status          = "done" if result.status == "done" else "failed"
        review.error_message            = result.error or None
        await db.commit()
        await db.refresh(review)

        yield _sse({"type": "done", "analysis": _review_to_out(review).model_dump(mode="json")})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ════════════════════════════════════════════════════════════════════════════════
# Retrieve cached analysis
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{repo_id}/{pr_number}/analysis",
    response_model=PRAnalysisOut,
    summary="Retrieve cached AI analysis (does not trigger a new run)",
)
async def get_analysis(
    repo_id: uuid.UUID,
    pr_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = await _get_review(repo_id, pr_number, db)
    if not review:
        raise HTTPException(
            status_code=404,
            detail="No analysis found for this PR. POST to /analyze first.",
        )
    return _review_to_out(review)


# ════════════════════════════════════════════════════════════════════════════════
# Human decision — approve / reject (writes back to GitHub)
# ════════════════════════════════════════════════════════════════════════════════

@router.post(
    "/{repo_id}/{pr_number}/decision",
    response_model=PRDecisionResponse,
    summary="Approve or reject a PR — writes the decision back to GitHub",
)
async def decide_pr(
    repo_id: uuid.UUID,
    pr_number: int,
    body: PRDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a human decision on a PR and apply it on GitHub.

    **action = "approve"**:
      - Posts a formal GitHub review with event=APPROVE
      - If `merge_on_approve=true`, also merges the PR using `merge_method`
        (requires write access on the connected GitHub account)

    **action = "reject"**:
      - Posts the `note` as a PR comment (if provided)
      - Closes the PR on GitHub (does not delete the branch)

    The decision is stored locally regardless of analysis status — a human
    can approve/reject even without running AI analysis first, though the
    UI should typically surface the AI recommendation alongside this action.

    Requires the current user's GitHub account (connected via OAuth) to have
    write access to the repository.
    """
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=403,
            detail="No GitHub access token on file. Connect your GitHub account via OAuth to take actions on PRs.",
        )

    github_result: dict = {}

    try:
        if body.action == "approve":
            review_body = body.note or "Approved via CodeNavigator."
            github_result = post_pr_review_comment(
                github_url   = repo.github_url,
                pr_number    = pr_number,
                access_token = repo.github_access_token or current_user.github_access_token,
                body         = review_body,
                event        = "APPROVE",
            )
            if body.merge_on_approve:
                merge_result = merge_pull_request(
                    github_url     = repo.github_url,
                    pr_number      = pr_number,
                    access_token   = current_user.github_access_token,
                    merge_method   = body.merge_method,
                )
                github_result["merge"] = merge_result

        else:  # reject
            github_result = close_pull_request(
                github_url   = repo.github_url,
                pr_number    = pr_number,
                access_token = repo.github_access_token or current_user.github_access_token,
                comment      = body.note,
            )

    except Exception as exc:
        logger.exception(f"GitHub action failed for PR #{pr_number}: {exc}")
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    # Persist the decision
    review = await _get_review(repo_id, pr_number, db)
    if not review:
        review = PullRequestReview(
            repository_id=repo_id, owner_id=current_user.id, pr_number=pr_number,
            analysis_status="not_analyzed",
        )
        db.add(review)

    decided_at = datetime.now(UTC)
    review.human_decision      = "approved" if body.action == "approve" else "rejected"
    review.human_decision_note = body.note or None
    review.human_decided_at    = decided_at
    await db.commit()

    return PRDecisionResponse(
        pr_number      = pr_number,
        human_decision = review.human_decision,
        github_action  = github_result,
        decided_at     = decided_at,
    )


# ════════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════════

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"




async def _get_review(
    repo_id: uuid.UUID, pr_number: int, db: AsyncSession,
) -> PullRequestReview | None:
    result = await db.execute(
        select(PullRequestReview).where(
            PullRequestReview.repository_id == repo_id,
            PullRequestReview.pr_number == pr_number,
        )
    )
    return result.scalar_one_or_none()


def _review_to_out(review: PullRequestReview) -> PRAnalysisOut:
    impact_raw = review.impact_analysis or {}
    return PRAnalysisOut(
        pr_number                = review.pr_number,
        repository_id            = review.repository_id,
        analysis_status          = review.analysis_status,
        summary                  = review.summary,
        code_review              = review.code_review,
        optimization_suggestions = review.optimization_suggestions,
        impact_analysis          = ImpactAnalysisOut(
            per_file                 = impact_raw.get("per_file", {}),
            total_dependent_files    = impact_raw.get("total_dependent_files", 0),
            total_affected_functions = impact_raw.get("total_affected_functions", 0),
            breaking_change_risk     = impact_raw.get("breaking_change_risk", "low"),
        ),
        ai_decision               = review.ai_decision,
        confidence_score          = review.confidence_score,
        risk_flags                = review.risk_flags or [],
        ai_decision_reason        = review.ai_decision_reason,
        total_tokens              = review.total_tokens,
        error_message             = review.error_message,
        human_decision            = review.human_decision or "pending",
        human_decision_note       = review.human_decision_note,
        created_at                = review.created_at,
        updated_at                = review.updated_at,
    )
