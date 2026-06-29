"""
Celery app + tasks.

The ingestion task runs the full pipeline in a background worker
so the API can return immediately with a task_id.
"""

from __future__ import annotations

import asyncio
import uuid

from celery import Celery
from loguru import logger

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "codenavigator",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True, name="tasks.ingest_repository", max_retries=2, default_retry_delay=30
)
def ingest_repository_task(self, repo_id: str, access_token: str | None = None) -> dict:
    """
    Background task: run full ingestion pipeline for a repository.
    repo_id: UUID string
    """
    logger.info(f"[Task {self.request.id}] Starting ingestion for repo {repo_id}")

    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.models.models import Repository
        from app.agents.repo_analyzer import run_ingestion
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Repository)
                .options(selectinload(Repository.indexed_by))
                .where(Repository.id == uuid.UUID(repo_id))
            )
            repo = result.scalar_one_or_none()

            if not repo:
                logger.error(f"Repo {repo_id} not found in DB")
                return {"status": "error", "message": "Repository not found"}

            try:
                await run_ingestion(repo, db, access_token=access_token)

            except Exception:
                await db.rollback()
                raise
            
            return {"status": "ready", "repo_id": repo_id}

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.exception(f"Ingestion task failed for {repo_id}: {exc}")

         # Last retry already used
        if self.request.retries >= self.max_retries:
            _run_async(
                mark_repo_failed(
                    repo_id,
                    str(exc),
                )
            )

            return {
                "status": "failed",
                "repo_id": repo_id,
                "error": str(exc),
            }

        raise self.retry(exc=exc)


@celery_app.task(
    bind=True, name="tasks.refresh_repository", max_retries=2, default_retry_delay=30
)
def refresh_repository_task(self, repo_id: str, access_token: str | None = None) -> dict:
    """
    Background task: incrementally refresh repository indexes from GitHub.
    """
    logger.info(f"[Task {self.request.id}] Starting refresh for repo {repo_id}")

    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.models.models import Repository
        from app.agents.repo_analyzer import run_repository_refresh
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Repository)
                .options(selectinload(Repository.indexed_by))
                .where(Repository.id == uuid.UUID(repo_id))
            )
            repo = result.scalar_one_or_none()

            if not repo:
                logger.error(f"Repo {repo_id} not found in DB")
                return {"status": "error", "message": "Repository not found"}

            try:
                return await run_repository_refresh(
                    repo,
                    db,
                    access_token=access_token,
                )
            except Exception:
                await db.rollback()
                raise

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.exception(f"Refresh task failed for {repo_id}: {exc}")

        if self.request.retries >= self.max_retries:
            _run_async(mark_repo_failed(repo_id, str(exc)))
            return {
                "status": "failed",
                "repo_id": repo_id,
                "error": str(exc),
            }

        raise self.retry(exc=exc)



async def mark_repo_failed(
    repo_id: str,
    error: str,
):
    from app.core.database import AsyncSessionLocal
    from app.models.models import Repository

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Repository).where(
                Repository.id == uuid.UUID(repo_id)
            )
        )

        repo = result.scalar_one_or_none()

        if repo:
            repo.status = "failed"
            repo.error_message = error
            await db.commit()
