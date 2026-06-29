"""
Repository Chat Agent — full RAG + graph pipeline.

Pipeline per request
────────────────────
1.  Intent classification  — categorise the question so retrieval can be tuned
2.  Embed question          — OpenAI text-embedding-3-small
3.  Qdrant search           — top-k enriched code chunks (filtered by repo + optional language)
4.  Neo4j graph enrichment  — for every distinct symbol in the retrieved chunks:
      • callers (who calls it)
      • callees (what it calls) — already in chunk metadata
      • class hierarchy (if it's a method)
      • file imports
5.  Prompt assembly         — system prompt + graph context + code context + history
6.  OpenRouter LLM call     — google/gemini-flash-1.5-8b  (fast, cheap, strong at code)
    Streaming variant yields token deltas as they arrive
7.  Return structured result — answer text + SourceCitation list + GraphRelation list + usage

Model choice
────────────
  google/gemini-flash-1.5-8b   ~$0.0375/$0.15 per M tokens
    → Best price/quality for code Q&A; 1M context window handles large contexts well.
  Fallback: google/gemini-flash-1.5  (2× cost, slightly better on complex reasoning)

  We do NOT use deepseek here because OpenRouter's deepseek endpoint has higher
  latency and occasional timeouts that hurt the streaming UX.
"""

from __future__ import annotations

import asyncio
import re
from time import perf_counter
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator

from loguru import logger
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.llm_models import resolve_chat_model
from app.schemas.schemas import GraphRelation, SourceCitation
from app.services.embeddings import embed_query
from app.services.evaluation_metrics import evaluate_rag_response
from app.services.graph_store import (
    get_callers,
    get_class_hierarchy,
    get_file_dependencies,
)
from app.services.vector_store import search_chunks
from app.agents.slash_commands import SlashCommandInvocation, parse_slash_command

settings = get_settings()

# ── Model config ───────────────────────────────────────────────────────────────
#
# Primary:  google/gemini-flash-1.5-8b  — fast, cheap, great at code
# Fallback: google/gemini-flash-1.5     — if primary fails
#
CHAT_MODEL = settings.chat_model  # google/gemini-flash-1.5-8b by default
CHAT_MODEL_FALLBACK = settings.chat_model_fallback  # google/gemini-flash-1.5 by default
MAX_TOKENS = 2048
TEMPERATURE = 0.15  # low = more deterministic / code-accurate


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are CodeNavigator, an expert AI software engineer embedded inside a codebase exploration tool.

You receive:
  • RETRIEVED CHUNKS  — actual source code from the repository, annotated with file path,
    symbol name, parameters, return type, complexity and call-graph edges.
  • GRAPH CONTEXT     — structural relationships extracted from the Neo4j knowledge graph:
    callers, imports, class hierarchy.

Your job is to answer the developer's question using only this context.

Output rules
────────────
1. Write in clear, developer-friendly Markdown.
2. For every code snippet you show, always specify the language in the fence:
     ```python
     def foo(): ...
     ```
3. When referencing a symbol, use inline code: `AuthService.login()` in `src/auth/service.py`.
4. When explaining a flow or sequence, number the steps.
5. When the question is about "what calls X" or "what does X call", use the GRAPH CONTEXT section.
6. If the context does not contain enough information to answer, say so explicitly —
   never hallucinate file names, function names, or behaviour.
7. Keep answers focused. Avoid repeating the source code verbatim unless the question
   explicitly asks for the full implementation.
8. At the end of your answer, if relevant, suggest a follow-up question the developer might want to ask.
"""


# ── Intent classifier ──────────────────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[str, str]] = [
    # (regex pattern, intent label)  — ORDER MATTERS: first match wins
    (r"\b(what calls|who calls|callers? of|called by)\b", "callers"),
    (r"\b(what does .* call|calls? to|dependencies of|depends on)\b", "callees"),
    (
        r"\b(deploy|docker|ci[\s/-]?cd|pipeline|build|infra|nginx|kubernetes|k8s)\b",
        "infra",
    ),
    (r"\b(test|spec|coverage|assert|mock|fixture|unittest|pytest)\b", "test"),
    (r"\b(auth|login|jwt|token|session|permission|role|oauth)\b", "auth"),
    (r"\b(database|db|query|schema|model|table|migration|orm|sql)\b", "data"),
    (r"\b(api|endpoint|route|controller|handler|request|response|rest)\b", "api"),
    (r"\b(how does|how do|how is|walk me through|trace|flow)\b", "trace"),
    (r"\b(where is|where are|find|locate|which file|which files)\b", "locate"),
    (r"\b(what does|explain|describe|overview|purpose|what is)\b", "explain"),
]


def classify_intent(question: str) -> str:
    q = question.lower()
    for pattern, label in _INTENT_PATTERNS:
        if re.search(pattern, q):
            return label
    return "general"


# ── Symbol extractor (from question text) ─────────────────────────────────────


def extract_mentioned_symbols(question: str) -> list[str]:
    """
    Pull out identifiers the developer explicitly mentioned.
    e.g. "What does AuthService.login() do?" → ["AuthService", "login"]
    Used to broaden the graph context query.
    """
    # Match CamelCase, snake_case, or dotted identifiers
    tokens = re.findall(
        r"\b([A-Z][a-zA-Z0-9]+|[a-z_][a-z0-9_]{2,}(?:\.[a-z_][a-z0-9_]+)?)\b", question
    )
    # Filter out common English stop-words
    stop = {
        "what",
        "does",
        "how",
        "where",
        "which",
        "find",
        "explain",
        "describe",
        "the",
        "this",
        "that",
        "and",
        "with",
        "for",
        "from",
        "into",
        "use",
        "all",
        "any",
        "each",
        "every",
        "can",
        "will",
        "are",
        "not",
        "about",
        "tell",
        "show",
        "list",
        "get",
        "give",
        "make",
        "its",
        "has",
        "have",
        "do",
        "is",
        "it",
        "in",
        "of",
        "to",
        "a",
        "an",
        "my",
        "me",
        "our",
        "code",
        "function",
        "method",
        "class",
        "file",
        "module",
        "project",
    }
    return [t for t in tokens if t.lower() not in stop][:8]


# ── Prompt assembly ────────────────────────────────────────────────────────────


def _format_chunk_for_prompt(idx: int, chunk: dict) -> str:
    path = chunk["file_path"]
    lang = chunk.get("language", "")
    symbol_type = chunk.get("symbol_type", "code")
    symbol_name = chunk.get("symbol_name")
    parent = chunk.get("parent_class")
    meta = chunk.get("metadata", {})

    # Heading
    if symbol_name:
        fqname = f"{parent}.{symbol_name}" if parent else symbol_name
        heading = f"[{idx}] `{path}` — **{symbol_type}**: `{fqname}`"
    else:
        s, e = chunk.get("start_line", 0), chunk.get("end_line", 0)
        heading = f"[{idx}] `{path}` — lines {s + 1}–{e + 1}"

    # Inline metadata hints
    hints: list[str] = []
    if meta.get("return_type"):
        hints.append(f"→ `{meta['return_type']}`")
    if meta.get("complexity", 1) > 3:
        hints.append(f"complexity {meta['complexity']}")
    if meta.get("calls"):
        calls_str = ", ".join(f"`{c}`" for c in meta["calls"][:5])
        hints.append(f"calls {calls_str}")
    if meta.get("decorators"):
        hints.append(f"decorators: {', '.join(meta['decorators'])}")

    hint_line = f"  _{'; '.join(hints)}_" if hints else ""

    body = chunk.get("raw_body", chunk.get("content", ""))
    return f"#### {heading}{hint_line}\n```{lang}\n{body}\n```"


def _format_graph_section(relations: list[GraphRelation]) -> str:
    if not relations:
        return ""
    lines = ["#### Graph relationships"]
    for r in relations:
        sym_part = f" → `{r.symbol}`" if r.symbol else ""
        file_part = f" _(in `{r.file_path}`)_" if r.file_path else ""
        lines.append(f"- **{r.kind}**: {r.label}{sym_part}{file_part}")
    return "\n".join(lines)


def _build_prompt(
    question: str,
    chunks: list[dict],
    relations: list[GraphRelation],
    history: list[dict],
    intent: str,
    command: SlashCommandInvocation | None = None,
) -> list[dict]:
    code_section = "\n\n".join(
        _format_chunk_for_prompt(i + 1, c) for i, c in enumerate(chunks)
    )
    graph_section = _format_graph_section(relations)

    context_parts = [f"### Retrieved code chunks (intent: {intent})\n\n{code_section}"]
    if graph_section:
        context_parts.append(f"### Knowledge graph context\n\n{graph_section}")

    context = "\n\n---\n\n".join(context_parts)

    system_prompt = SYSTEM_PROMPT
    if command:
        system_prompt += (
            "\n\nSlash command mode\n"
            "------------------\n"
            f"The developer used `{command.command.token}` ({command.command.title}). "
            f"{command.command.prompt_instruction}\n"
            "Still follow the general output rules and use only retrieved context."
        )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # History — last 6 turns only to keep context window lean
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append(
        {
            "role": "user",
            "content": (
                f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
                f"**Question:** {question}"
            ),
        }
    )
    return messages


def _resolve_command(question: str) -> tuple[str, str, SlashCommandInvocation | None]:
    """Return effective question, intent, and parsed slash command if present."""
    command = parse_slash_command(question)
    if not command:
        return question, classify_intent(question), None

    effective_question = command.effective_question
    return effective_question, command.command.intent, command


# ── Neo4j graph enrichment ─────────────────────────────────────────────────────


async def _fetch_graph_relations(
    chunks: list[dict],
    repo_id: str,
    mentioned_symbols: list[str],
) -> list[GraphRelation]:
    """
    Pull graph relationships for:
      - The top-scored symbol chunk
      - Any symbol names the developer explicitly mentioned
    Best-effort — never raises.
    """
    relations: list[GraphRelation] = []

    async def _safe(coro, label: str):
        try:
            return await coro
        except Exception as exc:
            logger.debug(f"Graph fetch [{label}] skipped: {exc}")
            return []

    # Gather symbol names to look up
    symbols_to_query: set[str] = set(mentioned_symbols)
    top_chunks_with_symbols = [c for c in chunks[:4] if c.get("symbol_name")]
    for c in top_chunks_with_symbols:
        symbols_to_query.add(c["symbol_name"])

    file_paths_queried: set[str] = set()

    # Run all graph queries concurrently
    tasks = []

    for sym in list(symbols_to_query)[:5]:
        tasks.append(
            ("callers", sym, _safe(get_callers(repo_id, sym), f"callers:{sym}"))
        )
        tasks.append(
            ("hierarchy", sym, _safe(get_class_hierarchy(repo_id, sym), f"hier:{sym}"))
        )

    # File dependencies for unique file paths in top chunks
    for c in chunks[:3]:
        fp = c.get("file_path")
        if fp and fp not in file_paths_queried:
            file_paths_queried.add(fp)
            tasks.append(
                ("deps", fp, _safe(get_file_dependencies(repo_id, fp), f"deps:{fp}"))
            )

    results = await asyncio.gather(*[t[2] for t in tasks])

    for (kind, name, _), result in zip(tasks, results):
        if not result:
            continue

        if kind == "callers":
            for row in result[:4]:
                relations.append(
                    GraphRelation(
                        kind="caller",
                        label=f"Called by `{row['caller']}()`",
                        file_path=row.get("file_path"),
                        symbol=row.get("caller"),
                    )
                )

        elif kind == "hierarchy":
            # result is a list of class names forming the chain
            chain = result if isinstance(result, list) else []
            if len(chain) > 1:
                relations.append(
                    GraphRelation(
                        kind="hierarchy",
                        label=" → ".join(f"`{c}`" for c in chain),
                        symbol=name,
                    )
                )

        elif kind == "deps":
            modules = [r["module"] for r in result[:5]]
            if modules:
                relations.append(
                    GraphRelation(
                        kind="dependency",
                        label=f"Imports: {', '.join(f'`{m}`' for m in modules)}",
                        file_path=name,
                    )
                )

    return relations


# ── Source citation builder ────────────────────────────────────────────────────


def _build_citations(chunks: list[dict]) -> list[SourceCitation]:
    return [
        SourceCitation(
            file_path=c["file_path"],
            language=c.get("language"),
            symbol_type=c.get("symbol_type"),
            symbol_name=c.get("symbol_name"),
            parent_class=c.get("parent_class"),
            start_line=c.get("start_line"),
            end_line=c.get("end_line"),
            relevance_score=round(c.get("score", 0.0), 4),
            snippet=(c.get("raw_body") or c.get("content", ""))[:200].strip(),
        )
        for c in chunks
    ]


# ── LLM client ─────────────────────────────────────────────────────────────────


def _llm() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            # OpenRouter best-practice headers
            "HTTP-Referer": "https://codenavigator.dev",
            "X-Title": "CodeNavigator",
        },
    )


# ── Public API: sync ───────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    answer: str
    sources: list[SourceCitation]
    relations: list[GraphRelation]
    usage: dict[str, int] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    intent: str = "general"
    command: str | None = None
    model: str = CHAT_MODEL


async def run_rag(
    question: str,
    repo_id: str,
    history: list[dict] | None = None,
    top_k: int = 8,
    language_filter: str | None = None,
    include_graph: bool = True,
    model: str | None = None,
) -> AgentResult:
    """
    Full RAG pipeline — returns a complete AgentResult.
    Use this for the synchronous (non-streaming) endpoint.
    """
    started_at = perf_counter()
    selected_model = resolve_chat_model(model)
    effective_question, intent, command = _resolve_command(question)
    mentioned = extract_mentioned_symbols(effective_question)

    retrieval_started_at = perf_counter()
    query_vector = await embed_query(effective_question)

    if command:
        top_k = max(top_k, command.command.top_k)
        include_graph = command.command.include_graph

    chunks = await search_chunks(
        query_vector,
        repo_id=repo_id,
        top_k=top_k,
        language_filter=language_filter,
    )
    retrieval_latency_ms = int((perf_counter() - retrieval_started_at) * 1000)

    if not chunks:
        answer = (
            "I couldn't find relevant code for your question in this repository.\n\n"
            "**Suggestions:**\n"
            "- Make sure the repository has finished indexing (check status)\n"
            "- Try rephrasing with specific function or class names\n"
            "- Use the semantic search endpoint to explore what's indexed"
        )
        return AgentResult(
            answer=answer,
            sources=[],
            relations=[],
            metrics=evaluate_rag_response(
                answer=answer,
                sources=[],
                total_latency_ms=int((perf_counter() - started_at) * 1000),
                retrieval_latency_ms=retrieval_latency_ms,
            ),
            intent=intent,
            command=command.command.name if command else None,
            model=selected_model,
        )

    relations: list[GraphRelation] = []
    if include_graph:
        relations = await _fetch_graph_relations(chunks, repo_id, mentioned)

    messages = _build_prompt(
        question=command.query if command and command.query else question,
        chunks=chunks,
        relations=relations,
        history=history or [],
        intent=intent,
        command=command,
    )

    logger.info(
        f"RAG → model={selected_model} chunks={len(chunks)} "
        f"relations={len(relations)} intent={intent} "
        f"command={command.command.name if command else None} repo={repo_id}"
    )

    actual_model = selected_model
    llm_started_at = perf_counter()
    try:
        resp = await _llm().chat.completions.create(
            model=selected_model,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
    except Exception as exc:
        logger.warning(f"Primary model failed ({exc}), retrying with fallback")
        actual_model = CHAT_MODEL_FALLBACK
        resp = await _llm().chat.completions.create(
            model=CHAT_MODEL_FALLBACK,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
    llm_latency_ms = int((perf_counter() - llm_started_at) * 1000)

    answer = resp.choices[0].message.content or ""
    sources = _build_citations(chunks)
    usage = {}
    if resp.usage:
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }

    return AgentResult(
        answer=answer,
        sources=sources,
        relations=relations,
        usage=usage,
        metrics=evaluate_rag_response(
            answer=answer,
            sources=sources,
            total_latency_ms=int((perf_counter() - started_at) * 1000),
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
        ),
        intent=intent,
        command=command.command.name if command else None,
        model=actual_model,
    )


# ── Public API: streaming ──────────────────────────────────────────────────────


async def run_rag_stream(
    question: str,
    repo_id: str,
    history: list[dict] | None = None,
    top_k: int = 8,
    language_filter: str | None = None,
    include_graph: bool = True,
    model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Streaming RAG pipeline.
    Yields SSE-compatible dicts (matching the SSE*Event schemas).

    Sequence:
      {"type": "start",     "session_id": ..., "message_id": ...}
      {"type": "delta",     "text": "..."}      ← one per token
      {"type": "sources",   "data": [...]}
      {"type": "relations", "data": [...]}
      {"type": "usage",     "data": {...}}
      {"type": "done"}
      {"type": "error",     "message": "..."}   ← only on failure
    """
    started_at = perf_counter()
    selected_model = resolve_chat_model(model)
    effective_question, intent, command = _resolve_command(question)
    mentioned = extract_mentioned_symbols(effective_question)
    retrieval_started_at = perf_counter()
    query_vector = await embed_query(effective_question)

    if command:
        top_k = max(top_k, command.command.top_k)
        include_graph = command.command.include_graph

    chunks = await search_chunks(
        query_vector,
        repo_id=repo_id,
        top_k=top_k,
        language_filter=language_filter,
    )
    retrieval_latency_ms = int((perf_counter() - retrieval_started_at) * 1000)

    message_id = str(uuid.uuid4())
    yield {
        "type": "start",
        "message_id": message_id,
        "intent": intent,
        "command": command.command.name if command else None,
        "model": selected_model,
    }

    if not chunks:
        answer = (
            "I couldn't find relevant code for your question in this repository.\n\n"
            "**Suggestions:**\n"
            "- Make sure the repository has finished indexing\n"
            "- Try rephrasing with specific function or class names\n"
            "- Use the semantic search endpoint to explore what's indexed"
        )
        yield {
            "type": "delta",
            "text": answer,
        }
        yield {"type": "sources", "data": []}
        yield {"type": "relations", "data": []}
        yield {
            "type": "metrics",
            "data": evaluate_rag_response(
                answer=answer,
                sources=[],
                total_latency_ms=int((perf_counter() - started_at) * 1000),
                retrieval_latency_ms=retrieval_latency_ms,
            ),
        }
        yield {"type": "done"}
        return

    # Fetch graph context before the LLM call so streamed answers can use it.
    relations: list[GraphRelation] = []
    if include_graph:
        relations = await _fetch_graph_relations(chunks, repo_id, mentioned)

    messages = _build_prompt(
        question=command.query if command and command.query else question,
        chunks=chunks,
        relations=relations,
        history=history or [],
        intent=intent,
        command=command,
    )

    try:
        stream = await _llm().chat.completions.create(
            model=selected_model,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
        )
    except Exception as exc:
        logger.warning(f"Primary model stream failed ({exc}), retrying fallback")
        try:
            stream = await _llm().chat.completions.create(
                model=CHAT_MODEL_FALLBACK,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=True,
            )
        except Exception as exc2:
            yield {"type": "error", "message": f"LLM unavailable: {exc2}"}
            yield {"type": "done"}
            return

    # Stream token deltas
    answer_parts: list[str] = []
    llm_latency_ms = 0
    llm_started_at = perf_counter()
    prompt_tokens = 0
    completion_tokens = 0
    async for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            answer_parts.append(delta)
            yield {"type": "delta", "text": delta}
        # Capture usage from final chunk (OpenRouter sends it on last event)
        if hasattr(event, "usage") and event.usage:
            prompt_tokens = event.usage.prompt_tokens or 0
            completion_tokens = event.usage.completion_tokens or 0
    llm_latency_ms = int((perf_counter() - llm_started_at) * 1000)

    sources = _build_citations(chunks)

    # Emit sources immediately after stream ends
    yield {
        "type": "sources",
        "data": [s.model_dump() for s in sources],
    }

    yield {
        "type": "relations",
        "data": [r.model_dump() for r in relations],
    }

    if prompt_tokens or completion_tokens:
        yield {
            "type": "usage",
            "data": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    yield {
        "type": "metrics",
        "data": evaluate_rag_response(
            answer="".join(answer_parts),
            sources=sources,
            total_latency_ms=int((perf_counter() - started_at) * 1000),
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
        ),
    }

    yield {"type": "done"}


# Generate Title for Chat


async def generate_chat_title(
    question: str,
    answer: str,
    model: str | None = None,
) -> str:
    selected_model = resolve_chat_model(model)
    response = await _llm().chat.completions.create(
        model=selected_model,
        messages=[
            {
                "role": "system",
                "content": """
                    Generate a concise conversation title.

                    Rules:
                    - 2 to 6 words
                    - Title Case
                    - No quotes
                    - No punctuation
                    - Return only the title
                """,
            },
            {
                "role": "user",
                "content": f"""
                    Question:
                    {question}

                    Assistant Answer:
                    {answer}
                """,
            },
        ],
        temperature=0.2,
        max_tokens=20,
    )

    return response.choices[0].message.content.strip()
