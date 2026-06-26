"""
Cross-encoder reranker using sentence-transformers CrossEncoder.

Jointly encodes (JD, resume) pairs and produces a relevance score.
Applied ONLY to top 100-200 candidates from retrieval (never all).
CPU-optimized with batch_size=8.
"""

from __future__ import annotations



from src.utils.logger import get_logger

logger = get_logger("cross_encoder_reranker")

# Global model cache
_cross_encoder = None


def _get_model(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """Load and cache the cross-encoder model."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder

        logger.info(f"Loading cross-encoder: {model_name}")
        _cross_encoder = CrossEncoder(model_name, max_length=512)
        logger.info("Cross-encoder loaded")
    return _cross_encoder


def rerank(
    jd_text: str,
    candidate_texts: list[str],
    candidate_ids: list[str],
    top_k: int = 100,
    batch_size: int = 8,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> list[tuple[str, float]]:
    """
    Rerank candidates using cross-encoder scoring.

    Creates (JD, resume) pairs and scores each with the cross-encoder.
    Returns top_k candidates sorted by cross-encoder score.

    Args:
        jd_text: Job description text.
        candidate_texts: List of resume texts to rerank.
        candidate_ids: Corresponding candidate IDs.
        top_k: Number of top candidates to return.
        batch_size: Batch size for CPU inference.
        model_name: Cross-encoder model name.

    Returns:
        List of (candidate_id, cross_encoder_score) tuples, sorted descending.
    """
    if not candidate_texts:
        return []

    model = _get_model(model_name)

    # Create pairs
    pairs = [[jd_text, resume_text] for resume_text in candidate_texts]

    # Score in batches
    logger.info(f"Cross-encoder reranking {len(pairs)} candidates (batch_size={batch_size})")
    scores = model.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=len(pairs) > 50,
    )

    # Pair scores with candidate IDs
    scored_candidates = list(zip(candidate_ids, scores.tolist()))

    # Sort by score descending
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    # Return top_k
    results = scored_candidates[:top_k]

    logger.info(
        f"Reranking complete: {len(candidate_texts)} → {len(results)} candidates, "
        f"score range: [{results[-1][1]:.4f}, {results[0][1]:.4f}]"
    )

    return results


def score_pair(
    jd_text: str,
    resume_text: str,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> float:
    """
    Score a single (JD, resume) pair.

    Args:
        jd_text: Job description text.
        resume_text: Resume text.
        model_name: Cross-encoder model name.

    Returns:
        Cross-encoder relevance score.
    """
    model = _get_model(model_name)
    score = model.predict([[jd_text, resume_text]])
    return float(score[0])
