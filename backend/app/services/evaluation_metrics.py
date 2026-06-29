from __future__ import annotations

import re
from statistics import mean
from typing import Any

from app.schemas.schemas import SourceCitation


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "your",
    "you",
    "are",
    "was",
    "were",
    "has",
    "have",
    "will",
    "can",
    "not",
    "into",
    "uses",
    "using",
    "code",
    "file",
    "function",
    "class",
    "method",
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOP_WORDS
    }


def _optional_bertscore(answer: str, reference_answer: str | None) -> float | None:
    """
    Uses bert-score only if the package is already installed.
    It is intentionally optional because it is large and downloads model weights.
    """
    if not reference_answer:
        return None
    try:
        from bert_score import score  # type: ignore

        _, _, f1 = score([answer], [reference_answer], lang="en", verbose=False)
        return round(float(f1.mean().item()), 4)
    except Exception:
        return None


def _recall_at_k(
    sources: list[SourceCitation],
    expected_files: list[str] | None,
    k: int = 5,
) -> float | None:
    if not expected_files:
        return None

    expected = {path.lower() for path in expected_files}
    retrieved = {source.file_path.lower() for source in sources[:k]}
    return round(len(expected & retrieved) / len(expected), 4)


def evaluate_rag_response(
    *,
    answer: str,
    sources: list[SourceCitation],
    total_latency_ms: int,
    retrieval_latency_ms: int | None = None,
    llm_latency_ms: int | None = None,
    expected_files: list[str] | None = None,
    reference_answer: str | None = None,
) -> dict[str, Any]:
    """
    Lightweight RAG metrics for production responses plus optional offline labels.

    Built-in metrics need no extra dependencies:
    - retrieval quality: top/average source relevance and optional Recall@5
    - answer grounding: lexical overlap between answer and retrieved snippets
    - hallucination risk: inverse of groundedness
    - performance: total/retrieval/LLM latency

    BERTScore is returned only when a reference answer is provided and the
    optional bert-score package is available.
    """
    relevance_scores = [source.relevance_score for source in sources]
    source_text = "\n".join(source.snippet for source in sources)
    answer_tokens = _tokens(answer)
    source_tokens = _tokens(source_text)

    if answer_tokens and source_tokens:
        groundedness = len(answer_tokens & source_tokens) / len(answer_tokens)
    else:
        groundedness = 0.0 if answer.strip() else 1.0

    groundedness = round(max(0.0, min(1.0, groundedness)), 4)

    return {
        "latency_ms": total_latency_ms,
        "retrieval_latency_ms": retrieval_latency_ms,
        "llm_latency_ms": llm_latency_ms,
        "retrieved_chunks": len(sources),
        "top_relevance_score": round(max(relevance_scores), 4)
        if relevance_scores
        else 0.0,
        "avg_relevance_score": round(mean(relevance_scores), 4)
        if relevance_scores
        else 0.0,
        "recall_at_5": _recall_at_k(sources, expected_files),
        "groundedness_score": groundedness,
        "hallucination_score": round(1.0 - groundedness, 4),
        "bertscore_f1": _optional_bertscore(answer, reference_answer),
    }
