"""
Candidate repository — CRUD operations on the candidates table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# pyrefly: ignore [missing-import]
from src.api.db_models import Candidate
# pyrefly: ignore [missing-import]
from src.utils.logger import get_logger

logger = get_logger("candidate_repo")


class CandidateRepository:
    """Async CRUD operations for the ``candidates`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> Candidate:
        """Create a new candidate record."""
        candidate = Candidate(**kwargs)
        self.session.add(candidate)
        await self.session.flush()
        logger.debug(f"Created candidate: {candidate.candidate_id}")
        return candidate

    async def get_by_id(self, candidate_id: str) -> Optional[Candidate]:
        """Fetch a candidate by ID."""
        result = await self.session.execute(
            select(Candidate).where(Candidate.candidate_id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, candidate_ids: list[str]) -> list[Candidate]:
        """Fetch multiple candidates by a list of IDs."""
        result = await self.session.execute(
            select(Candidate).where(Candidate.candidate_id.in_(candidate_ids))
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> list[Candidate]:
        """List candidates with optional status filter and pagination."""
        stmt = select(Candidate).offset(skip).limit(limit)
        if status:
            stmt = stmt.where(Candidate.processing_status == status)
        stmt = stmt.order_by(Candidate.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        candidate_id: str,
        status: str,
        **extra_fields,
    ) -> None:
        """Update the processing status of a candidate."""
        values = {
            "processing_status": status,
            "updated_at": datetime.now(timezone.utc),
            **extra_fields,
        }
        if status == "indexed":
            values["indexed_at"] = datetime.now(timezone.utc)
        await self.session.execute(
            update(Candidate)
            .where(Candidate.candidate_id == candidate_id)
            .values(**values)
        )
        logger.debug(f"Updated candidate {candidate_id} status → {status}")

    async def update_parsed_data(
        self,
        candidate_id: str,
        parsed_data: dict,
        skills: list,
        experience_years: float,
        education: list | dict,
        projects: list | None = None,
        certifications: list | None = None,
        links: dict | None = None,
    ) -> None:
        """Update parsed resume data for a candidate."""
        await self.session.execute(
            update(Candidate)
            .where(Candidate.candidate_id == candidate_id)
            .values(
                parsed_data=parsed_data,
                skills=skills,
                experience_years=experience_years,
                education=education,
                projects=projects,
                certifications=certifications,
                links=links,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def update_embedding_path(
        self, candidate_id: str, embedding_path: str
    ) -> None:
        """Set the embedding file path for a candidate."""
        await self.session.execute(
            update(Candidate)
            .where(Candidate.candidate_id == candidate_id)
            .values(
                embedding_path=embedding_path,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def update_feature_store_path(
        self, candidate_id: str, feature_store_path: str
    ) -> None:
        """Set the feature store Parquet path for a candidate."""
        await self.session.execute(
            update(Candidate)
            .where(Candidate.candidate_id == candidate_id)
            .values(
                feature_store_path=feature_store_path,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def delete(self, candidate_id: str) -> bool:
        """Delete a candidate and all associated data (cascade)."""
        candidate = await self.get_by_id(candidate_id)
        if candidate is None:
            return False
        await self.session.delete(candidate)
        logger.info(f"Deleted candidate: {candidate_id}")
        return True

    async def count(self, status: Optional[str] = None) -> int:
        """Count candidates with optional status filter."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Candidate)
        if status:
            stmt = stmt.where(Candidate.processing_status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one()
