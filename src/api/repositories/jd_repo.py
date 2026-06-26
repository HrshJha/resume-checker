"""
Job Description repository — CRUD operations on the job_descriptions table.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db_models import JobDescription
from src.utils.logger import get_logger

logger = get_logger("jd_repo")


class JDRepository:
    """Async CRUD operations for the ``job_descriptions`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> JobDescription:
        """Create a new job description record."""
        jd = JobDescription(**kwargs)
        self.session.add(jd)
        await self.session.flush()
        logger.debug(f"Created JD: {jd.jd_id}")
        return jd

    async def get_by_id(self, jd_id: str) -> Optional[JobDescription]:
        """Fetch a JD by its ID."""
        result = await self.session.execute(
            select(JobDescription).where(JobDescription.jd_id == jd_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        created_by: Optional[str] = None,
    ) -> list[JobDescription]:
        """List job descriptions with optional creator filter."""
        stmt = (
            select(JobDescription)
            .offset(skip)
            .limit(limit)
            .order_by(JobDescription.created_at.desc())
        )
        if created_by:
            stmt = stmt.where(JobDescription.created_by == created_by)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, jd_id: str) -> bool:
        """Delete a JD and all associated rankings (cascade)."""
        jd = await self.get_by_id(jd_id)
        if jd is None:
            return False
        await self.session.delete(jd)
        logger.info(f"Deleted JD: {jd_id}")
        return True

    async def count(self) -> int:
        """Count total job descriptions."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count()).select_from(JobDescription)
        )
        return result.scalar_one()
