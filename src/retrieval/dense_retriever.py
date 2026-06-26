"""
Dense retrieval using FAISS — supports IndexFlatIP, IndexHNSWFlat, IndexIVFPQ.

Loads pre-built FAISS index at startup and performs nearest-neighbor
search using cosine similarity (via inner product on L2-normalized vectors).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("dense_retriever")

# Global FAISS index and ID mapping
_faiss_index = None
_id_mapping: list[str] = []


def load_index(
    index_path: str,
    id_mapping_path: Optional[str] = None,
) -> None:
    """
    Load a pre-built FAISS index into memory.

    Args:
        index_path: Path to the .faiss index file.
        id_mapping_path: Path to numpy file mapping index positions to candidate_ids.
    """
    global _faiss_index, _id_mapping
    import faiss

    path = Path(index_path)
    if not path.exists():
        logger.warning(f"FAISS index not found: {index_path}")
        return

    _faiss_index = faiss.read_index(str(path))
    logger.info(
        f"Loaded FAISS index: {_faiss_index.ntotal} vectors, "
        f"dim={_faiss_index.d}"
    )

    # Load ID mapping
    if id_mapping_path and Path(id_mapping_path).exists():
        _id_mapping = list(np.load(id_mapping_path, allow_pickle=True))
        logger.info(f"Loaded ID mapping: {len(_id_mapping)} entries")


def build_index(
    embeddings: np.ndarray,
    candidate_ids: list[str],
    index_type: str = "IndexFlatIP",
    save_path: Optional[str] = None,
    hnsw_m: int = 32,
    hnsw_ef_construction: int = 200,
) -> None:
    """
    Build a FAISS index from embeddings.

    Args:
        embeddings: numpy array of shape (N, dim), L2-normalized.
        candidate_ids: List of candidate IDs (same order as embeddings).
        index_type: "IndexFlatIP", "IndexHNSWFlat", or "IndexIVFPQ".
        save_path: Optional path to save the index.
        hnsw_m: HNSW M parameter (neighbors per layer).
        hnsw_ef_construction: HNSW ef_construction parameter.
    """
    global _faiss_index, _id_mapping
    import faiss

    dim = embeddings.shape[1]
    n = embeddings.shape[0]

    logger.info(f"Building FAISS index: {n} vectors, dim={dim}, type={index_type}")

    if index_type == "IndexFlatIP":
        _faiss_index = faiss.IndexFlatIP(dim)
    elif index_type == "IndexHNSWFlat":
        _faiss_index = faiss.IndexHNSWFlat(dim, hnsw_m)
        _faiss_index.hnsw.efConstruction = hnsw_ef_construction
        _faiss_index.hnsw.efSearch = 200
    elif index_type == "IndexIVFPQ":
        nlist = min(1024, n // 10)
        quantizer = faiss.IndexFlatIP(dim)
        _faiss_index = faiss.IndexIVFPQ(quantizer, dim, nlist, 8, 8)
        _faiss_index.train(embeddings)
    else:
        raise ValueError(f"Unknown index type: {index_type}")

    _faiss_index.add(embeddings.astype(np.float32))
    _id_mapping = list(candidate_ids)

    logger.info(f"FAISS index built: {_faiss_index.ntotal} vectors")

    if save_path:
        save_dir = Path(save_path).parent
        save_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(_faiss_index, str(save_path))
        np.save(str(save_path).replace(".faiss", "_ids.npy"), np.array(candidate_ids))
        logger.info(f"Index saved to {save_path}")


def search(
    query_embedding: np.ndarray,
    top_k: int = 500,
) -> list[tuple[str, float]]:
    """
    Search the FAISS index for nearest neighbors.

    Args:
        query_embedding: Query vector of shape (dim,), L2-normalized.
        top_k: Number of results to return.

    Returns:
        List of (candidate_id, score) tuples, sorted by score descending.
    """
    if _faiss_index is None:
        logger.error("FAISS index not loaded")
        return []

    # Reshape for FAISS
    query = query_embedding.reshape(1, -1).astype(np.float32)

    # Search
    scores, indices = _faiss_index.search(query, min(top_k, _faiss_index.ntotal))

    results: list[tuple[str, float]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        if idx < len(_id_mapping):
            results.append((_id_mapping[idx], float(score)))

    return results


def get_index_size() -> int:
    """Return the number of vectors in the index."""
    if _faiss_index is None:
        return 0
    return _faiss_index.ntotal


def add_to_index(
    embedding: np.ndarray,
    candidate_id: str,
) -> None:
    """
    Add a single vector to the live index.

    Note: For IndexIVFPQ, this may not work well — prefer rebuild.
    """
    global _id_mapping
    if _faiss_index is None:
        logger.error("FAISS index not initialized")
        return

    vec = embedding.reshape(1, -1).astype(np.float32)
    _faiss_index.add(vec)
    _id_mapping.append(candidate_id)
