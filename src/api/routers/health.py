"""
Health check router.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from src.api.dependencies import get_settings
from src.api.models.request_models import HealthResponse
from src.retrieval import dense_retriever
from src.utils.logger import get_logger

logger = get_logger("health_router")

router = APIRouter()

# Set at application startup
_start_time = time.time()


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Check system health, model versions, and uptime."""
    settings = get_settings()

    return HealthResponse(
        status="healthy",
        model_versions={
            "embedding": settings.embedding_model,
            "cross_encoder": settings.cross_encoder_model,
            "ranker": settings.ranker_model_path,
        },
        faiss_index_size=dense_retriever.get_index_size(),
        uptime_seconds=round(time.time() - _start_time, 2),
        db_connection="ok",
    )
