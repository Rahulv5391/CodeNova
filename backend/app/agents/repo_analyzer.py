"""
Repository analysis and indexing pipeline.

The public entry points are:
  - run_ingestion: full repository indexing
  - run_repository_refresh: incremental indexing for changed files
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Repository
from app.services import graph_store, vector_store
from app.services.ast_extractor import extract_ast_metadata
from app.services.chunker import chunk_from_ast, detect_language
from app.services.embeddings import embed_texts
from app.services.github_service import (
    get_changed_files_since_commit,
    get_latest_commit_sha,
    load_repository,
)


EMBED_BATCH_SIZE = 50
MAX_CONCURRENT_AST = 8


@dataclass
class ProcessedFiles:
    chunks: list[dict]
    neo4j_metas: list[Any]
    total_functions: int
    total_classes: int
    languages: dict[str, int]
    skipped_files: int


async def run_ingestion(
    repo: Repository,
    db: AsyncSession,
    access_token: str | None = None,
) -> None:
    """
    Full pipeline. Updates repo.status at each stage.
    Called by the Celery worker.
    """
    repo_id = str(repo.id)

    try:
        await _set_status(repo, db, "cloning", progress=10)
        github_access_token = access_token or repo.indexed_by.github_access_token

        records, full_name, local_path = load_repository(
            github_url=repo.github_url,
            branch=repo.branch,
            access_token=github_access_token,
        )
        logger.info(f"[{full_name}] Loaded {len(records)} files")

        await _set_status(repo, db, "parsing", progress=25)
        processed = await _process_records(
            records,
            repo_id,
            error_prefix="File processing error",
        )
        logger.info(
            f"[{full_name}] Parsed {len(processed.chunks)} chunks from {len(records)} files"
        )

        await _set_status(repo, db, "graph_building", progress=55)
        graph_errors = await _write_graph_metadata(
            repo_id,
            processed.neo4j_metas,
            log_context=full_name,
        )

        await _set_status(repo, db, "embedding", progress=70)
        await _embed_and_upsert_chunks(
            processed.chunks,
            repo,
            db,
            log_context=full_name,
            update_indexed_chunks=True,
        )

        repo.total_files = len(records)
        repo.total_functions = processed.total_functions
        repo.total_classes = processed.total_classes
        repo.indexed_chunks = len(processed.chunks)
        repo.metadata_ = {
            "languages": processed.languages,
            "graph_errors": graph_errors,
            "local_path": str(local_path) if local_path else None,
        }
        await _set_status(repo, db, "ready", progress=100)
        logger.info(
            f"[{full_name}] Ingestion complete: "
            f"files={len(records)} chunks={len(processed.chunks)} "
            f"functions={processed.total_functions} classes={processed.total_classes}"
        )

    except Exception as exc:
        logger.exception(f"Ingestion failed for repo {repo_id}: {exc}")
        await _set_status(repo, db, "failed", progress=repo.progress, error=str(exc))
        raise


async def run_repository_refresh(
    repo: Repository,
    db: AsyncSession,
    access_token: str | None = None,
) -> dict:
    """
    Incrementally refresh one repository from GitHub.
    Compares the stored indexed SHA with branch head, removes stale per-file
    vector/graph data, and reindexes only changed files.
    """
    repo_id = str(repo.id)
    github_access_token = access_token or repo.indexed_by.github_access_token

    try:
        await _set_status(repo, db, "updating", progress=10)

        latest_sha = get_latest_commit_sha(
            repo.github_url,
            repo.branch,
            github_access_token,
        )
        if latest_sha and repo.indexed_commit_sha == latest_sha:
            repo.error_message = None
            await _set_status(repo, db, "ready", progress=100)
            return {
                "status": "ready",
                "repo_id": repo_id,
                "updated": False,
                "latest_sha": latest_sha,
            }

        if not repo.indexed_commit_sha:
            await run_ingestion(repo, db, access_token=github_access_token)
            return {
                "status": "ready",
                "repo_id": repo_id,
                "updated": True,
                "mode": "full_ingestion",
            }

        old_sha = repo.indexed_commit_sha
        changes = get_changed_files_since_commit(
            repo.github_url,
            old_sha,
            repo.branch,
            github_access_token,
        )
        delete_paths = sorted(
            set(changes.paths_to_delete + [r.path for r in changes.files_to_index])
        )
        logger.info(
            f"[{repo.full_name}] Refresh found {len(changes.files_to_index)} files to index "
            f"and {len(changes.paths_to_delete)} removed/renamed paths"
        )

        await _set_status(repo, db, "parsing", progress=25)
        if delete_paths:
            await vector_store.delete_file_chunks(repo_id, delete_paths)
            await graph_store.delete_file_graph(repo_id, delete_paths)

        processed = await _process_records(
            changes.files_to_index,
            repo_id,
            error_prefix="Refresh file processing error",
        )

        await _set_status(repo, db, "graph_building", progress=55)
        graph_errors = await _write_graph_metadata(
            repo_id,
            processed.neo4j_metas,
            log_context=repo.full_name,
        )

        await _set_status(repo, db, "embedding", progress=70)
        await _embed_and_upsert_chunks(
            processed.chunks,
            repo,
            db,
            log_context=repo.full_name,
            update_indexed_chunks=False,
        )

        repo.total_files = _count_tree_files(repo.tree_json or [])
        repo.indexed_commit_sha = changes.latest_sha
        repo.metadata_ = {
            **(getattr(repo, "metadata_", None) or {}),
            "last_refresh": {
                "from_sha": old_sha,
                "to_sha": changes.latest_sha,
                "indexed_files": [r.path for r in changes.files_to_index],
                "deleted_paths": changes.paths_to_delete,
                "languages": processed.languages,
                "graph_errors": graph_errors,
            },
        }
        await _set_status(repo, db, "ready", progress=100)

        return {
            "status": "ready",
            "repo_id": repo_id,
            "updated": True,
            "latest_sha": changes.latest_sha,
            "indexed_files": len(changes.files_to_index),
            "deleted_paths": len(changes.paths_to_delete),
        }

    except Exception as exc:
        logger.exception(f"Refresh failed for repo {repo_id}: {exc}")
        await _set_status(repo, db, "failed", progress=repo.progress, error=str(exc))
        raise


async def _set_status(
    repo: Repository,
    db: AsyncSession,
    status: str,
    progress: int | None = None,
    error: str | None = None,
) -> None:
    repo.status = status
    if progress is not None:
        repo.progress = progress
    if error:
        repo.error_message = error
    await db.commit()


async def _process_records(
    records: list[Any],
    repo_id: str,
    error_prefix: str,
) -> ProcessedFiles:
    sem = asyncio.Semaphore(MAX_CONCURRENT_AST)

    async def _process_file(record) -> tuple[list[dict], Any, str]:
        async with sem:
            return await asyncio.to_thread(_process_file_sync, record, repo_id)

    results = await asyncio.gather(
        *[_process_file(record) for record in records],
        return_exceptions=True,
    )

    chunks: list[dict] = []
    neo4j_metas: list[Any] = []
    total_functions = 0
    total_classes = 0
    languages: dict[str, int] = {}
    skipped_files = 0

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            skipped_files += 1
            logger.warning(f"{error_prefix} ({records[i].path}): {result}")
            continue

        file_chunks, meta, language = result
        chunks.extend(file_chunks)
        neo4j_metas.append(meta)
        total_functions += meta.total_functions
        total_classes += meta.total_classes
        languages[language] = languages.get(language, 0) + 1

    return ProcessedFiles(
        chunks=chunks,
        neo4j_metas=neo4j_metas,
        total_functions=total_functions,
        total_classes=total_classes,
        languages=languages,
        skipped_files=skipped_files,
    )


async def _write_graph_metadata(
    repo_id: str,
    neo4j_metas: list[Any],
    log_context: str,
) -> int:
    graph_errors = 0
    for meta in neo4j_metas:
        try:
            await graph_store.write_ast_metadata(repo_id, meta)
        except Exception as exc:
            graph_errors += 1
            logger.warning(f"Neo4j write failed for {meta.file_path}: {exc}")
            logger.exception(f"Neo4j write failed for {meta.file_path}")

    if graph_errors:
        logger.warning(f"[{log_context}] {graph_errors} Neo4j write errors")
    return graph_errors


async def _embed_and_upsert_chunks(
    chunks: list[dict],
    repo: Repository,
    db: AsyncSession,
    log_context: str,
    update_indexed_chunks: bool,
) -> None:
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        vectors = await embed_texts([chunk["content"] for chunk in batch])
        for chunk, vector in zip(batch, vectors):
            chunk["vector"] = vector

        await vector_store.upsert_chunks(batch)

        indexed_count = min(i + EMBED_BATCH_SIZE, len(chunks))
        if update_indexed_chunks:
            repo.indexed_chunks = indexed_count
        repo.progress = 70 + int((indexed_count / max(len(chunks), 1)) * 20)
        await db.commit()
        logger.debug(f"[{log_context}] embedded {indexed_count}/{len(chunks)}")


def _process_file_sync(record, repo_id: str):
    """
    Synchronous worker: AST extraction -> chunking -> build chunk dicts.
    Runs inside asyncio.to_thread so it does not block the event loop.
    """
    language = detect_language(record.extension)
    meta = extract_ast_metadata(record.content, record.path, language)
    raw_chunks = chunk_from_ast(meta, record.content)

    chunk_dicts = [
        {
            "repo_id": repo_id,
            "file_path": c.file_path,
            "language": c.language,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "raw_body": c.raw_body,
            "symbol_type": c.symbol_type,
            "symbol_name": c.symbol_name,
            "parent_class": c.parent_class,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "metadata": c.metadata,
        }
        for c in raw_chunks
    ]

    return chunk_dicts, meta, language


def _count_tree_files(nodes: list[dict]) -> int:
    total = 0
    for node in nodes:
        if node.get("type") == "file":
            total += 1
        else:
            total += _count_tree_files(node.get("children") or [])
    return total
