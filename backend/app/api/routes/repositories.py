"""
Repository routes:
  POST   /repos                   — ingest a new repo
  GET    /repos                   — list my repos
  GET    /repos/{id}              — repo detail
  DELETE /repos/{id}              — delete repo
  GET    /repos/{id}/status       — ingestion status (polling)
  GET    /repos/{id}/tree         — file tree
  GET    /repos/{id}/file         — single file content  (?path=...)
  GET    /repos/{id}/metrics      — repo stats
  GET    /repos/{id}/search       — semantic code search (?q=...)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.chat import _load_history, _get_or_create_default_session
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.models.models import Repository, User, ChatSession
from app.schemas.schemas import (
    RepoIngestRequest,
    RepoOut,
    RepoStatusOut,
    RepoIngestResponse,
    RepoPageResponse,
)

from app.services.github_service import (
    get_repo_description,
    get_latest_commit_sha,
    get_full_name,
    read_file_content,
    _clone_path,
    get_file_tree_from_github_api,
)

from app.services.vector_store import delete_repo_chunks
from app.services.graph_store import delete_repo_graph

router = APIRouter(prefix="/repos", tags=["repositories"])
settings = get_settings()

RUNNING_STATES = {
    "pending",
    "queued",
    "cloning",
    "parsing",
    "embedding",
    "graph_building",
    "updating",
}
TERMINAL_STATES = {"ready", "failed"}


@router.post(
    "", response_model=RepoIngestResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_repo(
    body: RepoIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    github_url = str(body.github_url)
    branch = body.branch.strip() or "main"
    request_access_token = (
        body.github_access_token.strip()
        if body.github_access_token and body.github_access_token.strip()
        else None
    )
    access_token = request_access_token or current_user.github_access_token

    # Prevent duplicate ingestion for same URL+branch per user
    existing = await db.execute(
        select(Repository).where(
            Repository.indexed_by_user_id == current_user.id,
            Repository.github_url == github_url,
            Repository.branch == branch,
        )
    )
    repo = existing.scalar_one_or_none()

    latest_commit_sha = get_latest_commit_sha(
        github_url,
        branch,
        access_token,
    )

    tree = get_file_tree_from_github_api(github_url, branch, access_token)

    if repo:
        if repo.status in RUNNING_STATES:
            return {"repo": repo, "tree": tree}

        if latest_commit_sha and repo.indexed_commit_sha == latest_commit_sha:
            # Repo with same version already present and Indexed
            return {"repo": repo, "tree": tree}

        # Repo Changed on Github
        repo.status = "updating"
        repo.progress = 0
        repo.error_message = None
        repo.tree_json = tree
        await db.flush()

    else:
        full_name = get_full_name(github_url)

        description = get_repo_description(
            github_url,
            access_token,
        )

        repo = Repository(
            indexed_by_user_id=current_user.id,
            github_url=github_url,
            full_name=full_name,
            branch=branch,
            description=description,
            status="pending",
            indexed_commit_sha=latest_commit_sha,
            tree_json=tree,
        )

        db.add(repo)
        await db.flush()

    from app.tasks import ingest_repository_task

    task = ingest_repository_task.delay(str(repo.id), request_access_token)
    repo.celery_task_id = task.id
    if repo.status == "pending":
        repo.status = "queued"
        repo.progress = 5

    if request_access_token:
        repo.github_access_token = request_access_token

    await db.commit()
    await db.refresh(repo)

    return {"repo": repo, "tree": tree}


@router.get("", response_model=list[RepoOut])
async def list_repos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Repository)
        .where(Repository.indexed_by_user_id == current_user.id)
        .order_by(Repository.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/{repo_id}/refresh",
    response_model=RepoIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_repo(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    if repo.status in RUNNING_STATES:
        return {"repo": repo, "tree": repo.tree_json or []}

    access_token = repo.github_access_token or current_user.github_access_token
    latest_commit_sha = get_latest_commit_sha(
        repo.github_url,
        repo.branch,
        access_token,
    )
    if not latest_commit_sha:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not fetch latest commit SHA from GitHub",
        )

    if repo.indexed_commit_sha == latest_commit_sha:
        repo.status = "ready"
        repo.progress = 100
        repo.error_message = None
        await db.commit()
        await db.refresh(repo)
        return {"repo": repo, "tree": repo.tree_json or []}

    tree = get_file_tree_from_github_api(repo.github_url, repo.branch, access_token)
    repo.tree_json = tree

    from app.tasks import refresh_repository_task

    repo.status = "updating"
    repo.progress = 5
    repo.error_message = None
    task = refresh_repository_task.delay(str(repo.id), access_token)
    repo.celery_task_id = task.id
    await db.commit()
    await db.refresh(repo)

    return {"repo": repo, "tree": repo.tree_json or []}


@router.get(
    "/{repo_id}",
    response_model=RepoPageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def get_repo_with_tree_and_chat(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo: Repository = await _get_repo_or_404(repo_id, current_user.id, db)
    session: ChatSession = await _get_or_create_default_session(
        repo.id, current_user.id, db
    )
    return {
        "repo": repo,
        "tree": repo.tree_json or [],
        "chat": {
            "session_id": session.id,
            "session_title": session.title,
            "messages": await _load_history(session.id, db),
        },
    }


@router.delete("/{repo_id}", status_code=status.HTTP_200_OK)
async def delete_repo(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_repo_or_404(repo_id, current_user.id, db)

    # Clean up vector + graph stores
    await delete_repo_chunks(str(repo_id))
    await delete_repo_graph(str(repo_id))

    await db.delete(repo)
    await db.commit()

    return {"message": "Deleted"}


@router.get("/{repo_id}/status", response_model=RepoStatusOut)
async def get_repo_status(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_repo_or_404(repo_id, current_user.id, db)
    return RepoStatusOut(
        id=repo.id,
        status=repo.status,
        celery_task_id=repo.celery_task_id,
        error_message=repo.error_message,
        total_files=repo.total_files,
        indexed_chunks=repo.indexed_chunks,
        progress=repo.progress,
    )


@router.get(
    "/{repo_id}/status/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Repository ingestion status events",
        }
    },
)
async def stream_repo_status(
    repo_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream repository ingestion status changes as Server-Sent Events.

    Event payloads are JSON:
        {"type": "status", "repo": RepoStatusOut}
        {"type": "done", "repo": RepoStatusOut}
        {"type": "error", "message": "..."}
    """
    user_id = current_user.id
    await _get_repo_or_404(repo_id, user_id, db)

    async def event_generator():
        last_payload: dict | None = None

        while True:
            if await request.is_disconnected():
                break

            async with AsyncSessionLocal() as stream_db:
                try:
                    repo = await _get_repo_or_404(repo_id, user_id, stream_db)
                except HTTPException as exc:
                    data = {"type": "error", "message": exc.detail}
                    yield f"data: {json.dumps(data)}\n\n"
                    break
                status_payload = _repo_status_payload(repo)

            if status_payload != last_payload:
                event_type = (
                    "done" if status_payload["status"] in TERMINAL_STATES else "status"
                )
                data = {"type": event_type, "repo": status_payload}
                yield f"data: {json.dumps(data)}\n\n"
                last_payload = status_payload

                if status_payload["status"] in TERMINAL_STATES:
                    break
            else:
                yield ": keep-alive\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# # ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_repo_or_404(
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
    return repo


def _assert_ready(repo: Repository) -> None:
    if repo.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Repository is not ready (current status: {repo.status})",
        )


def _local_path(repo: Repository) -> Path:
    return _clone_path(repo.full_name, repo.branch)


def _repo_status_payload(repo: Repository) -> dict:
    return RepoStatusOut(
        id=repo.id,
        status=repo.status,
        celery_task_id=repo.celery_task_id,
        error_message=repo.error_message,
        total_files=repo.total_files,
        indexed_chunks=repo.indexed_chunks,
        progress=repo.progress,
    ).model_dump(mode="json")
