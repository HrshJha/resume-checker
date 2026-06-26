"""
Hybrid retriever — fuses dense (FAISS) and sparse (BM25) results.

Combines scores: final = α × dense_score + (1-α) × normalized_bm25_score
Default α = 0.7 (dense-weighted).
"""

from __future__ import annotations

import numpy as np

from src.retrieval import bm25_retriever, dense_retriever
from src.utils.logger import get_logger

logger = get_logger("hybrid_retriever")


def hybrid_search(
    query_embedding: np.ndarray,
    query_text: str,
    top_k: int = 500,
    dense_weight: float = 0.7,
) -> list[tuple[str, float, float, float]]:
    """
    Hybrid search combining dense and sparse retrieval.

    Score fusion: final = dense_weight × dense_score + (1 - dense_weight) × bm25_norm

    Args:
        query_embedding: Dense embedding of the query (JD).
        query_text: Raw query text for BM25.
        top_k: Number of results to return.
        dense_weight: Weight for dense scores (0-1). Default 0.7.

    Returns:
        List of (candidate_id, hybrid_score, dense_score, bm25_score) tuples,
        sorted by hybrid_score descending.
    """
    bm25_weight = 1.0 - dense_weight

    # Retrieve from both indexes (get more candidates for fusion)
    dense_results = dense_retriever.search(query_embedding, top_k=top_k * 2)
    bm25_results = bm25_retriever.search(query_text, top_k=top_k * 2)

    # Build score dictionaries
    dense_scores: dict[str, float] = {cid: score for cid, score in dense_results}
    bm25_scores: dict[str, float] = {cid: score for cid, score in bm25_results}

    # Normalize BM25 scores to [0, 1] range
    if bm25_scores:
        bm25_max = max(bm25_scores.values())
        bm25_min = min(bm25_scores.values())
        bm25_range = bm25_max - bm25_min
        if bm25_range > 0:
            bm25_scores = {
                cid: (score - bm25_min) / bm25_range
                for cid, score in bm25_scores.items()
            }
        else:
            bm25_scores = {cid: 1.0 for cid in bm25_scores}

    # Normalize dense scores to [0, 1] range
    if dense_scores:
        dense_max = max(dense_scores.values())
        dense_min = min(dense_scores.values())
        dense_range = dense_max - dense_min
        if dense_range > 0:
            dense_scores = {
                cid: (score - dense_min) / dense_range
                for cid, score in dense_scores.items()
            }
        else:
            dense_scores = {cid: 1.0 for cid in dense_scores}

    # Union of all candidate IDs
    all_candidates = set(dense_scores.keys()) | set(bm25_scores.keys())

    # Compute hybrid scores
    results: list[tuple[str, float, float, float]] = []
    for cid in all_candidates:
        d_score = dense_scores.get(cid, 0.0)
        b_score = bm25_scores.get(cid, 0.0)
        hybrid = dense_weight * d_score + bm25_weight * b_score
        results.append((cid, hybrid, d_score, b_score))

    # Sort by hybrid score descending
    results.sort(key=lambda x: x[1], reverse=True)

    # Return top_k
    results = results[:top_k]

    logger.debug(
        f"Hybrid search: {len(dense_results)} dense + {len(bm25_results)} bm25 "
        f"→ {len(results)} fused (top_k={top_k})"
    )

    return results
