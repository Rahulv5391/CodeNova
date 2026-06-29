"""
Chat routes — all conversation endpoints.

Endpoints
─────────
POST   /chat/sessions                       Create a new chat session for a repo
GET    /chat/sessions                       List sessions (optionally filter by repo)
GET    /chat/sessions/{id}                  Session detail with full message history
DELETE /chat/sessions/{id}                  Delete session + all messages
PATCH  /chat/sessions/{id}                  Rename session title
POST   /chat/sessions/{id}/messages         Send a message → full sync response
POST   /chat/sessions/{id}/stream           Send a message → SSE stream response

Session model
─────────────
A session ties a user to a specific repo and carries the conversation history.
Every message is persisted so the LLM can use prior turns for context.

SSE contract (POST .../stream)
──────────────────────────────
Uses POST (not GET) so the question can be in the request body rather than
a query string — important for long questions.

The response is text/event-stream.  Each event is:
    data: <JSON object>\n\n

Event types (in order):
    {"type": "start",     "message_id": "<uuid>", "intent": "<label>"}
    {"type": "delta",     "text": "..."}          ← stream these to the UI
    {"type": "sources",   "data": [SourceCitation, ...]}
    {"type": "relations", "data": [GraphRelation,  ...]}
    {"type": "usage",     "data": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}}
    {"type": "message_ids", "user_message_id": "<uuid>", "assistant_message_id": "<uuid>"}
    {"type": "done"}
    {"type": "error",     "message": "..."}        ← on failure, then done

Frontend rendering
──────────────────
  • "delta" events → append ev.text to a Markdown string, render with react-markdown
  • "sources" event → populate a collapsible "Sources" drawer below the answer
      group by file_path, show snippet as hover tooltip, start_line as file-link anchor
  • "relations" event → render as a "Relationships" chip row above sources
  • "usage" → optional token counter badge
  • "done" → mark response complete, enable input again
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_agent import (
    AgentResult,
    run_rag,
    run_rag_stream,
    generate_chat_title,
)
from app.agents.slash_commands import (
    get_slash_command_catalog,
    parse_slash_command,
    unknown_slash_command,
)
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.llm_models import allowed_chat_models, resolve_chat_model
from app.models.models import ChatMessage, ChatSession, Repository, User
from app.schemas.schemas import (
    ChatModelOption,
    ChatModelsResponse,
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    GraphRelation,
    SlashCommandOut,
    SourceCitation,
    DeleteMessagesRequest,
)

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()


def _model_label(model: str) -> str:
    provider, _, name = model.partition("/")
    if not name:
        return model
    return f"{provider.title()} {name.replace('-', ' ').title()}"


@router.get(
    "/models",
    response_model=ChatModelsResponse,
    summary="List available OpenRouter chat models",
)
async def list_chat_models():
    default_model = settings.chat_model
    return ChatModelsResponse(
        default_model=default_model,
        models=[
            ChatModelOption(
                id=model,
                label=_model_label(model),
            )
            for model in allowed_chat_models()
        ],
    )


@router.get(
    "/commands",
    response_model=list[SlashCommandOut],
    summary="List supported chat slash commands",
)
async def list_slash_commands():
    """
    Return the curated slash commands the frontend should show in the chat box.
    """
    return get_slash_command_catalog()


# ════════════════════════════════════════════════════════════════════════════════
# Session management
# ════════════════════════════════════════════════════════════════════════════════


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
async def create_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new conversation session attached to a specific repository.
    The repo must belong to the current user and have status = 'ready'.
    """
    await _get_ready_repo(body.repository_id, current_user.id, db)

    session = ChatSession(
        user_id=current_user.id,
        repository_id=body.repository_id,
        title="New Chat",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get(
    "/sessions", response_model=list[ChatSessionOut], summary="List chat sessions"
)
async def list_sessions(
    repository_id: uuid.UUID | None = Query(default=None, description="Filter by repo"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
    )
    if repository_id:
        q = q.where(ChatSession.repository_id == repository_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetail,
    summary="Get session with full message history",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_session_or_404(session_id, current_user.id, db)

    # Load repo for display name
    repo_result = await db.execute(
        select(Repository).where(Repository.id == session.repository_id)
    )
    repo = repo_result.scalar_one_or_none()

    msgs_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msgs_result.scalars().all()

    return ChatSessionDetail(
        session=ChatSessionOut.model_validate(session),
        messages=[_to_message_out(m) for m in messages],
        repo_full_name=repo.full_name if repo else "",
    )


@router.patch(
    "/sessions/{session_id}", response_model=ChatSessionOut, summary="Rename a session"
)
async def rename_session(
    session_id: uuid.UUID,
    title: str = Body(..., embed=True, min_length=1, max_length=120),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_session_or_404(session_id, current_user.id, db)
    session.title = title
    await db.commit()
    await db.refresh(session)
    return session


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session and all its messages",
)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_session_or_404(session_id, current_user.id, db)
    await db.delete(session)
    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# Messaging — synchronous
# ════════════════════════════════════════════════════════════════════════════════


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatResponse,
    summary="Send a message and get a full response (sync)",
)
async def send_message(
    session_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full synchronous endpoint — waits for the complete LLM response before
    returning. Good for non-streaming clients or server-side usage.

    Response shape
    ──────────────
    {
      "session_id": "...",
      "message": {
        "id":             "...",
        "session_id":     "...",
        "role":           "assistant",
        "content":        "Markdown string — render with react-markdown",
        "sources": [
          {
            "file_path":       "src/auth/service.py",
            "language":        "python",
            "symbol_type":     "method",
            "symbol_name":     "login",
            "parent_class":    "AuthService",
            "start_line":      42,
            "end_line":        78,
            "relevance_score": 0.9312,
            "snippet":         "def login(email, password):..."
          },
          ...
        ],
        "graph_relations": [
          {
            "kind":      "caller",
            "label":     "Called by `UserController.authenticate()`",
            "file_path": "src/controllers/user.py",
            "symbol":    "authenticate"
          },
          ...
        ],
        "created_at": "2024-01-01T00:00:00Z"
      },
      "usage": {"prompt_tokens": 1200, "completion_tokens": 340, "total_tokens": 1540}
    }
    """
    session = await _get_session_or_404(session_id, current_user.id, db)
    _validate_slash_message(body.question)
    selected_model = resolve_chat_model(body.model)
    history = await _load_history(session_id, db)

    is_first_message = len(history) == 0

    # Persist user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.question,
        sources=[],
    )
    db.add(user_msg)
    await db.flush()

    # Run full RAG pipeline
    result: AgentResult = await run_rag(
        question=body.question,
        repo_id=str(session.repository_id),
        history=history,
        top_k=body.top_k,
        language_filter=body.language_filter,
        include_graph=body.include_graph,
        model=selected_model,
    )

    # Persist assistant message
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result.answer,
        sources=[s.model_dump() for s in result.sources],
        graph_relations=[r.model_dump() for r in result.relations],
        intent=result.intent,
        usage=result.usage or None,
    )
    db.add(assistant_msg)

    if is_first_message:
        session.title = await generate_chat_title(
            question=body.question,
            answer=result.answer,
            model=selected_model,
        )

    await db.commit()
    await db.refresh(assistant_msg)

    return ChatResponse(
        session_id=session_id,
        session_title=session.title,
        message=_to_message_out(assistant_msg),
        model=result.model,
        usage=result.usage or None,
        metrics=result.metrics or None,
    )


# ════════════════════════════════════════════════════════════════════════════════
# Messaging — SSE streaming
# ════════════════════════════════════════════════════════════════════════════════


@router.post(
    "/sessions/{session_id}/stream",
    summary="Send a message and stream the response (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Server-Sent Events stream",
        }
    },
)
async def stream_message(
    session_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Streaming endpoint using Server-Sent Events (SSE).

    Uses POST (not GET) so the full question travels in the request body,
    avoiding URL-length limits on long questions.

    The response Content-Type is `text/event-stream`.
    Each event is a line:
        data: <JSON>\\n\\n

    Event sequence:
        {"type": "start",     "message_id": "<uuid>", "intent": "<label>"}
        {"type": "delta",     "text": "..."}           ← append to displayed Markdown
        {"type": "sources",   "data": [...]}            ← SourceCitation[]
        {"type": "relations", "data": [...]}            ← GraphRelation[]
        {"type": "usage",     "data": {...}}            ← token counts
        {"type": "message_ids", "user_message_id": "<uuid>", "assistant_message_id": "<uuid>"}
        {"type": "done"}

    On error:
        {"type": "error", "message": "..."}
        {"type": "done"}

    Frontend integration example (fetch + ReadableStream):

        const resp = await fetch(`/api/v1/chat/sessions/${sessionId}/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json',
                     'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ question, top_k: 8, include_graph: true })
        })

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\\n\\n')
          buffer = lines.pop()          // keep incomplete chunk
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const ev = JSON.parse(line.slice(6))
            if (ev.type === 'delta')     setAnswer(a => a + ev.text)
            if (ev.type === 'sources')   setSources(ev.data)
            if (ev.type === 'relations') setRelations(ev.data)
            if (ev.type === 'usage')     setUsage(ev.data)
            if (ev.type === 'message_ids') updateMessageIds(ev)
            if (ev.type === 'done')      setStreaming(false)
            if (ev.type === 'error')     setError(ev.message)
          }
        }
    """
    session = await _get_session_or_404(session_id, current_user.id, db)
    _validate_slash_message(body.question)
    selected_model = resolve_chat_model(body.model)
    history = await _load_history(session_id, db)

    is_first_message = len(history) == 0

    # Persist user message synchronously before streaming begins
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.question,
        sources=[],
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    async def event_generator():
        full_text: list[str] = []
        final_sources: list[dict] = []
        final_relations: list[dict] = []

        try:
            async for event in run_rag_stream(
                question=body.question,
                repo_id=str(session.repository_id),
                history=history,
                top_k=body.top_k,
                language_filter=body.language_filter,
                include_graph=body.include_graph,
                model=selected_model,
            ):
                event_type = event.get("type")

                if event_type == "delta":
                    full_text.append(event["text"])

                elif event_type == "sources":
                    final_sources = event["data"]

                elif event_type == "relations":
                    final_relations = event["data"]

                elif event_type == "error":
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                elif event_type == "done":
                    continue

                # Emit every event directly to the client
                yield f"data: {json.dumps(event, default=str)}\n\n"

        except Exception as exc:
            from loguru import logger

            logger.exception(f"Streaming error for session {session_id}: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Persist the completed assistant message
        try:
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content="".join(full_text),
                sources=final_sources,
                graph_relations=final_relations,
            )
            db.add(assistant_msg)

            if is_first_message:
                session.title = await generate_chat_title(
                    body.question,
                    assistant_msg.content,
                    model=selected_model,
                )

            await db.commit()
            await db.refresh(assistant_msg)

            message_ids_event = {
                "type": "message_ids",
                "user_message_id": str(user_msg.id),
                "assistant_message_id": str(assistant_msg.id),
            }
            yield f"data: {json.dumps(message_ids_event)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:
            from loguru import logger

            logger.warning(f"Failed to persist stream message: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to persist streamed message.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
async def delete_messages(
    body: DeleteMessagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not body.message_ids:
        raise HTTPException(
            status_code=400,
            detail="No message IDs provided."
        )
    
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.id.in_(body.message_ids),
            ChatMessage.session_id.in_(
                select(ChatSession.id).where(
                    ChatSession.user_id == current_user.id
                )
            ),
        )
    )

    await db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# Private helpers
# ════════════════════════════════════════════════════════════════════════════════


def _validate_slash_message(question: str) -> None:
    unknown = unknown_slash_command(question)
    if unknown:
        supported = [item["command"] for item in get_slash_command_catalog()]
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Unsupported slash command: {unknown}",
                "supported_commands": supported,
            },
        )

    invocation = parse_slash_command(question)
    if invocation and invocation.command.requires_query and not invocation.query:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"{invocation.command.token} needs a search query.",
                "usage": invocation.command.usage,
            },
        )


async def _get_session_or_404(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def _get_ready_repo(
    repo_id: uuid.UUID,
    indexed_by_user_id: uuid.UUID,
    db: AsyncSession,
) -> Repository:
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.indexed_by_user_id == indexed_by_user_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repo.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Repository not ready (status: {repo.status}). "
            f"Poll /repos/{repo_id}/status until status = 'ready'.",
        )
    return repo


async def _load_history(
    session_id: uuid.UUID,
    db: AsyncSession,
    max_turns: int = 10,
) -> list[dict]:
    """Load last N turns of conversation history for the LLM context."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max_turns * 2)  # 2 messages per turn
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


def _to_message_out(msg: ChatMessage) -> ChatMessageOut:
    """Convert ORM ChatMessage → ChatMessageOut Pydantic model."""
    sources: list[SourceCitation] = []
    for s in msg.sources or []:
        try:
            sources.append(SourceCitation(**s))
        except Exception:
            pass

    relations: list[GraphRelation] = []
    for r in msg.graph_relations or []:
        try:
            relations.append(GraphRelation(**r))
        except Exception:
            pass

    return ChatMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        sources=sources,
        graph_relations=relations,
        created_at=msg.created_at,
    )


async def _get_or_create_default_session(
    repo_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.repository_id == repo_id,
            ChatSession.user_id == user_id,
        )
        .order_by(ChatSession.created_at.desc())
        .limit(1)
    )

    session = result.scalar_one_or_none()

    if session:
        return session

    session = ChatSession(
        repository_id=repo_id,
        user_id=user_id,
        title="New Chat",
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return session
