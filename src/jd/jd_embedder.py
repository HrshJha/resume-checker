"""
JD embedder — generates dense embeddings for job descriptions.

Uses sentence-transformers (BGE-base or MiniLM) for embedding.
Embeddings are L2-normalized for cosine similarity via inner product.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("jd_embedder")

# Global model cache
_embedding_model = None


def _get_model(model_name: str = "BAAI/bge-base-en-v1.5"):
    """Load and cache the sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Model loaded: dim={_embedding_model.get_sentence_embedding_dimension()}")
    return _embedding_model


def embed_text(
    text: str,
    model_name: str = "BAAI/bge-base-en-v1.5",
    normalize: bool = True,
) -> np.ndarray:
    """
    Generate a dense embedding for text.

    Args:
        text: Input text to embed.
        model_name: Sentence transformer model name.
        normalize: If True, L2-normalize the embedding.

    Returns:
        numpy array of shape (dim,) with float32 values.
    """
    model = _get_model(model_name)
    embedding = model.encode(
        text,
        normalize_embeddings=normalize,
        show_progress_bar=False,
    )
    return embedding.astype(np.float32)


def embed_texts_batch(
    texts: list[str],
    model_name: str = "BAAI/bge-base-en-v1.5",
    normalize: bool = True,
    batch_size: int = 32,
) -> np.ndarray:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts: List of texts to embed.
        model_name: Model name.
        normalize: L2-normalize embeddings.
        batch_size: Encoding batch size.

    Returns:
        numpy array of shape (N, dim) with float32 values.
    """
    model = _get_model(model_name)
    embeddings = model.encode(
        texts,
        normalize_embeddings=normalize,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
    )
    return embeddings.astype(np.float32)


def embed_jd(
    jd_text: str,
    required_skills: list[str] | None = None,
    model_name: str = "BAAI/bge-base-en-v1.5",
    save_path: Optional[str] = None,
) -> dict[str, np.ndarray]:
    """
    Generate multi-vector embeddings for a job description.

    Embeds:
    - Full JD text
    - Skills concatenated as a sentence
    - Required skills specifically

    Args:
        jd_text: Full JD text.
        required_skills: List of required skill names.
        model_name: Embedding model name.
        save_path: Optional path to save embeddings.

    Returns:
        Dict of embedding arrays: {"full", "skills"}.
    """
    embeddings: dict[str, np.ndarray] = {}

    # Full text embedding
    embeddings["full"] = embed_text(jd_text, model_name)

    # Skills embedding (if available)
    if required_skills:
        skills_text = ", ".join(required_skills)
        embeddings["skills"] = embed_text(skills_text, model_name)

    # Save if path provided
    if save_path:
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        for key, emb in embeddings.items():
            np.save(str(save_dir / f"jd_{key}.npy"), emb)
        logger.debug(f"Saved JD embeddings to {save_path}")

    return embeddings


def get_embedding_dimension(model_name: str = "BAAI/bge-base-en-v1.5") -> int:
    """Get the embedding dimension of the model."""
    model = _get_model(model_name)
    return model.get_sentence_embedding_dimension()
