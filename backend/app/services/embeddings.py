"""
Embedding service — wraps OpenAI text-embedding-3-small.
Batches texts to stay within API limits, retries on rate errors.
"""
from __future__ import annotations

import asyncio

from loguru import logger
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()

_client: AsyncOpenAI | None = None

BATCH_SIZE = 100  # texts per API call
MAX_TOKENS_PER_TEXT = 8191


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _embed_batch(texts: list[str]) -> list[list[float]]:
    resp = await _get_client().embeddings.create(
        model=settings.embed_model,
        input=texts,
    )
    return [item.embedding for item in resp.data]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, batching as needed."""
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]

    for batch in batches:
        embeddings = await _embed_batch(batch)
        all_embeddings.extend(embeddings)
        # small sleep to be kind to rate limits
        if len(batches) > 1:
            await asyncio.sleep(0.2)

    logger.debug(f"Embedded {len(texts)} texts in {len(batches)} batch(es)")
    return all_embeddings


async def embed_query(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]
