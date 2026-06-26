"""
BM25 sparse retrieval using rank-bm25.

Provides keyword-based retrieval as the sparse component
of the hybrid search pipeline.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from src.utils.logger import get_logger

logger = get_logger("bm25_retriever")

# Global BM25 index
_bm25_index: Optional[BM25Okapi] = None
_candidate_ids: list[str] = []
_corpus: list[list[str]] = []


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    text = text.lower()
    tokens = re.findall(r"\b\w+\b", text)
    return [t for t in tokens if len(t) > 1]


def build_bm25_index(
    documents: list[str],
    candidate_ids: list[str],
) -> None:
    """
    Build BM25 index from document texts.

    Args:
        documents: List of resume full texts.
        candidate_ids: Corresponding candidate IDs.
    """
    global _bm25_index, _candidate_ids, _corpus

    _corpus = [_tokenize(doc) for doc in documents]
    _candidate_ids = list(candidate_ids)
    _bm25_index = BM25Okapi(_corpus)

    logger.info(f"Built BM25 index: {len(_corpus)} documents")


def search(
    query: str,
    top_k: int = 500,
) -> list[tuple[str, float]]:
    """
    Search BM25 index with a text query.

    Args:
        query: Search query text.
        top_k: Number of results to return.

    Returns:
        List of (candidate_id, bm25_score) tuples.
    """
    if _bm25_index is None:
        logger.error("BM25 index not built")
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scores = _bm25_index.get_scores(query_tokens)

    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:top_k]

    results: list[tuple[str, float]] = []
    for idx in top_indices:
        if scores[idx] > 0:
            results.append((_candidate_ids[idx], float(scores[idx])))

    return results


def get_index_size() -> int:
    """Return number of documents in BM25 index."""
    return len(_corpus)
