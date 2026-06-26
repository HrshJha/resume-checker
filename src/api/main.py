"""
FastAPI main application — entry point with lifespan, middleware, and routing.

Startup loads all ML models, FAISS index, and database connections.
All routers mounted under /api/v1/ prefix.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.database import close_db, create_all_tables, init_db
from src.api.dependencies import get_settings
from src.utils.logger import get_logger, setup_logger

logger = get_logger("main")

# Track startup time for health endpoint
_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan — startup and shutdown logic.

    Startup:
    1. Initialize logging
    2. Initialize database
    3. Create data directories
    4. (Optional) Load ML models and FAISS index

    Shutdown:
    1. Close database connections
    """
    global _start_time
    _start_time = time.time()

    settings = get_settings()

    # 1. Setup logging
    setup_logger(level=settings.log_level, json_output=False)
    logger.info("Starting Candidate Intelligence System...")

    # 2. Initialize database
    await init_db(settings.db_url, echo=settings.log_level == "DEBUG")
    await create_all_tables()
    logger.info("Database initialized")

    # 3. Create required directories
    for dir_path in [
        settings.upload_dir,
        "data/raw/resumes",
        "data/raw/job_descriptions",
        "data/processed",
        "data/embeddings",
        "models/ranker",
        "models/embeddings",
        "models/authenticity",
        "models/registry",
    ]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # 4. (Lazy) Model loading happens on first request via service layer

    logger.info(f"CIS started in {time.time() - _start_time:.2f}s")

    yield

    # Shutdown
    await close_db()
    logger.info("CIS shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Candidate Intelligence System",
        description="AI-powered Resume Screening and Candidate Ranking API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # --- CORS Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Request Logging Middleware ---
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)"
        )
        return response

    # --- Global Exception Handler ---
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_code": "INTERNAL_ERROR",
            },
        )

    # --- Mount Routers ---
    from src.api.routers import auth, candidates, health, jobs, search

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Job Descriptions"])
    app.include_router(candidates.router, prefix="/api/v1/candidates", tags=["Candidates"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["Search & Ranking"])
    app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])

    return app


# Create the application instance
app = create_app()
