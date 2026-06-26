"""
Database engine, session factory, and declarative Base for SQLAlchemy 2.0.

Supports both SQLite (development) and PostgreSQL (production) via the
``DB_URL`` environment variable. Uses async sessions.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.utils.logger import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


# ---------------------------------------------------------------------------
# Engine and session factory (initialized at startup via ``init_db``)
# ---------------------------------------------------------------------------
_engine = None
_async_session_factory = None


async def init_db(db_url: str, echo: bool = False) -> None:
    """
    Initialize the async database engine and session factory.

    Args:
        db_url: Database connection URL (async driver).
        echo: If True, log all SQL statements.
    """
    global _engine, _async_session_factory

    # Determine connect_args based on database type
    connect_args = {}
    if "sqlite" in db_url:
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(
        db_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info(f"Database engine initialized: {db_url.split('@')[-1] if '@' in db_url else db_url}")


async def close_db() -> None:
    """Dispose the database engine."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_session)):
            ...
    """
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Create all tables defined by ORM models (dev/testing only)."""
    if _engine is None:
        raise RuntimeError("Database not initialized.")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All database tables created")
