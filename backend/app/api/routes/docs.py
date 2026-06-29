"""
Documentation generation routes.

Endpoints
─────────
GET  /docs/topics                    List all available topic IDs with descriptions
POST /docs/generate/{repo_id}        Generate documentation (sync, may take 30-90s)
GET  /docs/generate/{repo_id}/stream Stream generation progress via SSE
GET  /docs                           List past documentation runs for the current user
GET  /docs/{doc_id}                  Retrieve a previously generated document
DELETE /docs/{doc_id}                Delete a generated document

Generation model
────────────────
Each topic is a separate focused LLM call (google/gemini-flash-1.5).
All topics run in parallel via asyncio.gather — a 15-topic generation
takes roughly the same time as a single call (~15-25s).

The assembled Markdown document is persisted to the DB so it can be retrieved
later without regenerating.

SSE streaming contract (GET .../stream)
───────────────────────────────────────
Because generation is slow, the stream endpoint emits progress events so
the frontend can show a live progress bar.

Events (in order):
  {"type": "start",    "total_topics": N, "topic_ids": [...]}
  {"type": "progress", "topic_id": "...", "title": "...", "status": "generating"}
  {"type": "section",  "topic_id": "...", "title": "...", "content": "...",
                        "status": "done"|"skipped"|"error", "tokens_used": N}
  {"type": "done",     "doc_id": "...", "total_tokens": N, "status": "done"|"partial"}
  {"type": "error",    "message": "..."}

Frontend integration example:

  const resp = await fetch(`/api/v1/docs/generate/${repoId}/stream?topics=api_reference,architecture`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  const reader = resp.body.getReader()
  ...
  if (ev.type === 'progress')  updateProgressBar(ev.topic_id)
  if (ev.type === 'section')   addSection(ev.topic_id, ev.content)
  if (ev.type === 'done')      finalize(ev.doc_id)
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.agents.doc_agent import (
    ALL_TOPICS,
    TOPIC_MAP,
    SectionResult,
    TopicSpec,
    _fetch_chunks_for_topic,
    _fetch_graph_context_for_topic,
    _format_chunks_for_doc,
    _generate_section,
    _assemble_document,
    generate_documentation,
)
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import GeneratedDoc, Repository, User
from app.api.routes.repositories import _get_repo_or_404, _assert_ready
from app.schemas.schemas import (
    DocDetailResponse,
    DocGenerateRequest,
    DocGenerateResponse,
    DocListItem,
    DocSectionOut,
    TopicInfo,
)

router = APIRouter(prefix="/docs", tags=["documentation"])


# ════════════════════════════════════════════════════════════════════════════════
# Topic catalogue
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/topics",
    response_model=list[TopicInfo],
    summary="List all available documentation topics",
)
async def list_topics():
    """
    Returns the full catalogue of documentation topic IDs.
    Pass any subset of these IDs in the `topics` field of the generate request.
    Pass an empty list to generate all topics.

    Example response:
    ```json
    [
      { "id": "project_overview",  "title": "Project Overview",           "description": "..." },
      { "id": "api_reference",     "title": "API Reference",              "description": "..." },
      { "id": "architecture",      "title": "System Architecture",        "description": "..." },
      ...
    ]
    ```
    """
    return [
        TopicInfo(id=t.id, title=t.title, description=t.description)
        for t in ALL_TOPICS
    ]


# ════════════════════════════════════════════════════════════════════════════════
# Synchronous generation
# ════════════════════════════════════════════════════════════════════════════════

@router.post(
    "/generate/{repo_id}",
    response_model=DocGenerateResponse,
    summary="Generate documentation (synchronous — waits for completion)",
    status_code=status.HTTP_201_CREATED,
)
async def generate_docs(
    repo_id: uuid.UUID,
    body: DocGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate technical documentation for a repository.

    All topics are generated in parallel — typical wall-clock time:
      • 5 topics  →  ~10-15 s
      • 10 topics →  ~15-25 s
      • 15 topics →  ~20-35 s

    The result is persisted and retrievable via GET /docs/{doc_id}.

    **Topics**: pass a list of topic IDs from GET /docs/topics.
    Pass `[]` or `["all"]` to generate all 15 topics.

    **user_context**: optional free text about the project, e.g.
    `"This is a multi-tenant B2B SaaS. The payments module uses Stripe."`

    **format**:
    - `"markdown"` (default) — `full_document` contains the assembled Markdown
    - `"json"` — `full_document` is `""`, only `sections` is populated

    Response shape → see `DocGenerateResponse` schema.
    """
    repo = await _get_ready_repo(repo_id, current_user.id, db)

    # Resolve topic list
    topic_ids = _resolve_topics(body.topics)
    format = body.format.lower()

    # Create DB record (status = pending)
    doc_record = GeneratedDoc(
        repository_id = repo_id,
        owner_id      = current_user.id,
        topics        = topic_ids,
        user_context  = body.user_context or None,
        status        = "generating",
        content       = "",
        sections      = {},
        format        = format
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)

    # Run generation
    result = await generate_documentation(
        repo_id        = str(repo_id),
        repo_full_name = repo.full_name,
        github_url     = repo.github_url,
        topic_ids      = topic_ids,
        user_context   = body.user_context,
        doc_id         = str(doc_record.id),
    )

    # Persist result
    full_doc = result.full_document if body.format == "markdown" else ""
    doc_record.content       = full_doc
    doc_record.sections      = result.sections
    doc_record.status        = result.status
    doc_record.total_tokens  = result.total_tokens
    if result.status == "failed":
        doc_record.error_message = "All topic generations failed."
    await db.commit()

    # Build response sections in requested order
    sections_out = _sections_to_out(result.sections, topic_ids)

    return DocGenerateResponse(
        doc_id           = doc_record.id,
        repository_id    = repo_id,
        repo_full_name   = repo.full_name,
        topics_requested = topic_ids,
        sections         = sections_out,
        full_document    = full_doc,
        total_tokens     = result.total_tokens,
        status           = result.status,
        generated_at     = datetime.now(UTC),
        format           = format
    )


# ════════════════════════════════════════════════════════════════════════════════
# SSE streaming generation
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/generate/{repo_id}/stream",
    summary="Generate documentation with SSE progress stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def generate_docs_stream(
    repo_id: uuid.UUID,
    topics: str = Query(
        default="",
        description="Comma-separated topic IDs. Leave empty for all topics.",
    ),
    user_context: str = Query(default="", max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SSE streaming generation — emits one event per topic as it completes.

    **topics** query param: comma-separated IDs, e.g.
    `?topics=project_overview,api_reference,architecture`
    Leave empty for all topics.

    SSE event sequence:

    ```
    data: {"type": "start",    "total_topics": 3, "topic_ids": [...]}

    data: {"type": "progress", "topic_id": "project_overview",
                               "title": "Project Overview", "status": "generating"}

    data: {"type": "section",  "topic_id": "project_overview",
                               "title": "Project Overview",
                               "content": "## Project Overview\\n\\n...",
                               "status": "done", "tokens_used": 412}

    data: {"type": "progress", "topic_id": "api_reference", ...}
    data: {"type": "section",  "topic_id": "api_reference",  ...}

    data: {"type": "done",     "doc_id": "uuid", "total_tokens": 3201,
                               "status": "done", "full_document": "# Repo..."}

    data: {"type": "error",    "message": "..."}   ← only on fatal failure
    ```
    """
    repo = await _get_ready_repo(repo_id, current_user.id, db)

    topic_ids = _resolve_topics(
        [t.strip() for t in topics.split(",") if t.strip()] if topics else []
    )
    specs = [TOPIC_MAP[tid] for tid in topic_ids if tid in TOPIC_MAP]

    # Create pending DB record
    doc_record = GeneratedDoc(
        repository_id = repo_id,
        owner_id      = current_user.id,
        topics        = topic_ids,
        user_context  = user_context or None,
        status        = "generating",
        content       = "",
        sections      = {},
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)
    doc_id = str(doc_record.id)

    async def event_stream():
        import asyncio

        yield _sse({"type": "start", "total_topics": len(specs), "topic_ids": topic_ids, "doc_id": doc_id})

        collected_sections: dict[str, dict] = {}
        total_tokens = 0
        has_error    = False

        for spec in specs:
            # Emit "generating" progress event before the LLM call
            yield _sse({"type": "progress", "topic_id": spec.id, "title": spec.title, "status": "generating"})

            try:
                result = await _generate_section(
                    spec           = spec,
                    repo_id        = str(repo_id),
                    repo_full_name = repo.full_name,
                    user_context   = user_context,
                )

                section_dict = {
                    "title":       result.title,
                    "content":     result.content,
                    "status":      result.status,
                    "error":       result.error,
                    "tokens_used": result.tokens_used,
                }
                collected_sections[result.topic_id] = section_dict
                total_tokens += result.tokens_used
                if result.status == "error":
                    has_error = True

                # Emit the completed section immediately
                yield _sse({
                    "type":        "section",
                    "topic_id":    result.topic_id,
                    "title":       result.title,
                    "content":     result.content,
                    "status":      result.status,
                    "tokens_used": result.tokens_used,
                    "error":       result.error,
                })

            except Exception as exc:
                logger.exception(f"Stream section error ({spec.id}): {exc}")
                has_error = True
                yield _sse({"type": "section", "topic_id": spec.id, "title": spec.title,
                            "content": "", "status": "error", "error": str(exc), "tokens_used": 0})

        # Assemble full document from all completed sections
        ordered = [
            SectionResult(
                topic_id    = tid,
                title       = collected_sections[tid]["title"],
                content     = collected_sections[tid]["content"],
                status      = collected_sections[tid]["status"],
                tokens_used = collected_sections[tid]["tokens_used"],
            )
            for tid in topic_ids
            if tid in collected_sections and collected_sections[tid]["status"] in ("done", "skipped")
        ]
        full_document = _assemble_document(repo.full_name, repo.github_url, ordered)

        final_status = "partial" if has_error else "done"

        # Persist to DB
        try:
            doc_record.content      = full_document
            doc_record.sections     = collected_sections
            doc_record.status       = final_status
            doc_record.total_tokens = total_tokens
            await db.commit()
        except Exception as exc:
            logger.warning(f"Failed to persist streamed doc {doc_id}: {exc}")

        yield _sse({
            "type":          "done",
            "doc_id":        doc_id,
            "total_tokens":  total_tokens,
            "status":        final_status,
            "full_document": full_document,
        })

    return StreamingResponse(
        event_stream(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ════════════════════════════════════════════════════════════════════════════════
# CRUD — list / get / delete past docs
# ════════════════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=list[DocListItem],
    summary="List documentation runs for the current user",
)
async def list_docs(
    repository_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(GeneratedDoc)
        .where(GeneratedDoc.owner_id == current_user.id)
        .order_by(GeneratedDoc.created_at.desc())
        .limit(limit)
    )
    if repository_id:
        q = q.where(GeneratedDoc.repository_id == repository_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/{doc_id}",
    response_model=DocDetailResponse,
    summary="Retrieve a previously generated document",
)
async def get_doc(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_doc_or_404(doc_id, current_user.id, db)

    # Fetch repo for display name
    repo_result = await db.execute(
        select(Repository).where(Repository.id == doc.repository_id)
    )
    repo = repo_result.scalar_one_or_none()

    # Rebuild sections list in original topic order
    sections_out = _sections_to_out(doc.sections, doc.topics)

    return DocDetailResponse(
        id             = doc.id,
        repository_id  = doc.repository_id,
        repo_full_name = repo.full_name if repo else "",
        topics         = doc.topics,
        user_context   = doc.user_context,
        sections       = sections_out,
        full_document  = doc.content,
        status         = doc.status,
        total_tokens   = doc.total_tokens,
        created_at     = doc.created_at,
        updated_at     = doc.updated_at,
        format         = doc.format
    )


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a generated document",
)
async def delete_doc(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_doc_or_404(doc_id, current_user.id, db)
    await db.delete(doc)
    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════════

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


def _resolve_topics(topic_ids: list[str]) -> list[str]:
    """Return ordered list of valid topic IDs. Empty / ['all'] → all topics."""
    if not topic_ids or topic_ids == ["all"]:
        return [t.id for t in ALL_TOPICS]
    valid = [tid for tid in topic_ids if tid in TOPIC_MAP]
    unknown = [tid for tid in topic_ids if tid not in TOPIC_MAP]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown topic IDs: {unknown}. "
                   f"Call GET /api/v1/docs/topics for the full list.",
        )
    return valid


def _sections_to_out(
    sections: dict,
    ordered_topic_ids: list[str],
) -> list[DocSectionOut]:
    out: list[DocSectionOut] = []
    for tid in ordered_topic_ids:
        if tid not in sections:
            continue
        s = sections[tid]
        out.append(DocSectionOut(
            topic_id    = tid,
            title       = s.get("title", tid),
            content     = s.get("content", ""),
            status      = s.get("status", "unknown"),
            error       = s.get("error", ""),
            tokens_used = s.get("tokens_used", 0),
        ))
    return out


async def _get_ready_repo(
    repo_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> Repository:
    repo = await _get_repo_or_404(repo_id, owner_id, db)
    _assert_ready(repo)
    return repo


async def _get_doc_or_404(
    doc_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> GeneratedDoc:
    result = await db.execute(
        select(GeneratedDoc).where(
            GeneratedDoc.id       == doc_id,
            GeneratedDoc.owner_id == owner_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
