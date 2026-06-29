"""
Qdrant vector store client.

Each indexed code chunk is stored as a point:
  vector:  1536-dim OpenAI text-embedding-3-small
  payload: repo_id, file_path, language, chunk_index, content, raw_body,
           symbol_type, symbol_name, parent_class, start_line, end_line,
           metadata (params, return_type, complexity, calls, …)
"""

from __future__ import annotations

import uuid

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings

settings = get_settings()
VECTOR_DIM = 1536  # text-embedding-3-small


def _client() -> AsyncQdrantClient:
    kwargs: dict = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return AsyncQdrantClient(**kwargs)


async def ensure_collection() -> None:
    qc = _client()
    collections = await qc.get_collections()
    existing = {c.name for c in collections.collections}
    if settings.qdrant_collection not in existing:
        await qc.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection: {settings.qdrant_collection}")
    await qc.close()


async def upsert_chunks(chunks: list[dict]) -> None:
    """
    Each chunk dict must have 'vector' set before calling this.
    Extra keys are stored as payload.
    """
    qc = _client()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=chunk["vector"],
            payload={
                "repo_id": chunk["repo_id"],
                "file_path": chunk["file_path"],
                "language": chunk.get("language", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk["content"],
                "raw_body": chunk.get("raw_body", chunk["content"]),
                "symbol_type": chunk.get("symbol_type", "code"),
                "symbol_name": chunk.get("symbol_name"),
                "parent_class": chunk.get("parent_class"),
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
                "metadata": chunk.get("metadata", {}),
            },
        )
        for chunk in chunks
    ]
    await qc.upsert(collection_name=settings.qdrant_collection, points=points)
    await qc.close()
    logger.debug(f"Upserted {len(points)} chunks → Qdrant")


async def search_chunks(
    query_vector: list[float],
    repo_id: str,
    top_k: int = 8,
    language_filter: str | None = None,
    symbol_type_filter: str | None = None,
) -> list[dict]:
    """
    Vector similarity search scoped to one repo.
    Optional filters: language, symbol_type (function/class/method/code).
    """
    qc = _client()

    must = [FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
    if language_filter:
        must.append(
            FieldCondition(key="language", match=MatchValue(value=language_filter))
        )
    if symbol_type_filter:
        must.append(
            FieldCondition(
                key="symbol_type", match=MatchValue(value=symbol_type_filter)
            )
        )

    response = await qc.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=Filter(must=must),
        limit=top_k,
        with_payload=True,
    )

    results = response.points
    await qc.close()

    return [
        {
            "score": hit.score,
            "file_path": hit.payload["file_path"],
            "language": hit.payload.get("language"),
            "content": hit.payload["content"],
            "raw_body": hit.payload.get("raw_body", hit.payload["content"]),
            "symbol_type": hit.payload.get("symbol_type"),
            "symbol_name": hit.payload.get("symbol_name"),
            "parent_class": hit.payload.get("parent_class"),
            "start_line": hit.payload.get("start_line"),
            "end_line": hit.payload.get("end_line"),
            "metadata": hit.payload.get("metadata", {}),
        }
        for hit in results
    ]


async def delete_repo_chunks(repo_id: str) -> None:
    qc = _client()
    await qc.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
        ),
    )
    await qc.close()
    logger.info(f"Deleted all Qdrant chunks for repo {repo_id}")


async def delete_file_chunks(repo_id: str, file_paths: list[str]) -> None:
    if not file_paths:
        return

    qc = _client()
    for file_path in file_paths:
        await qc.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="repo_id", match=MatchValue(value=repo_id)),
                    FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                ]
            ),
        )
    await qc.close()
    logger.info(f"Deleted Qdrant chunks for {len(file_paths)} files in repo {repo_id}")
