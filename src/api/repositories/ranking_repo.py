"""
Ranking repository — CRUD operations on rankings and explanations tables.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db_models import Explanation, Ranking
from src.utils.logger import get_logger

logger = get_logger("ranking_repo")


class RankingRepository:
    """Async CRUD operations for ``rankings`` and ``explanations`` tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- Rankings -----

    async def create_ranking(self, **kwargs) -> Ranking:
        """Create a new ranking entry."""
        ranking = Ranking(**kwargs)
        self.session.add(ranking)
        await self.session.flush()
        return ranking

    async def bulk_create_rankings(self, rankings_data: list[dict]) -> list[Ranking]:
        """Create multiple ranking entries in bulk."""
        rankings = [Ranking(**data) for data in rankings_data]
        self.session.add_all(rankings)
        await self.session.flush()
        logger.debug(f"Bulk created {len(rankings)} rankings")
        return rankings

    async def get_rankings_for_jd(
        self,
        jd_id: str,
        top_k: int = 20,
    ) -> list[Ranking]:
        """Get ranked candidates for a JD, ordered by rank."""
        result = await self.session.execute(
            select(Ranking)
            .where(Ranking.jd_id == jd_id)
            .order_by(Ranking.rank.asc())
            .limit(top_k)
        )
        return list(result.scalars().all())

    async def get_ranking(
        self, jd_id: str, candidate_id: str
    ) -> Optional[Ranking]:
        """Get a specific ranking for a JD-candidate pair."""
        result = await self.session.execute(
            select(Ranking).where(
                Ranking.jd_id == jd_id,
                Ranking.candidate_id == candidate_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_rankings_for_jd(self, jd_id: str) -> int:
        """Delete all rankings for a JD (e.g., before re-ranking)."""
        result = await self.session.execute(
            delete(Ranking).where(Ranking.jd_id == jd_id)
        )
        count = result.rowcount  # type: ignore
        logger.debug(f"Deleted {count} rankings for JD {jd_id}")
        return count

    # ----- Explanations -----

    async def create_explanation(self, **kwargs) -> Explanation:
        """Create a new explanation for a ranking."""
        explanation = Explanation(**kwargs)
        self.session.add(explanation)
        await self.session.flush()
        return explanation

    async def bulk_create_explanations(
        self, explanations_data: list[dict]
    ) -> list[Explanation]:
        """Create multiple explanations in bulk."""
        explanations = [Explanation(**data) for data in explanations_data]
        self.session.add_all(explanations)
        await self.session.flush()
        logger.debug(f"Bulk created {len(explanations)} explanations")
        return explanations

    async def get_explanation_for_ranking(
        self, ranking_id: str
    ) -> Optional[Explanation]:
        """Get the explanation associated with a ranking."""
        result = await self.session.execute(
            select(Explanation).where(Explanation.ranking_id == ranking_id)
        )
        return result.scalar_one_or_none()

    async def get_explanation_for_pair(
        self, jd_id: str, candidate_id: str
    ) -> Optional[Explanation]:
        """Get explanation by JD-candidate pair (via ranking join)."""
        result = await self.session.execute(
            select(Explanation)
            .join(Ranking, Explanation.ranking_id == Ranking.ranking_id)
            .where(
                Ranking.jd_id == jd_id,
                Ranking.candidate_id == candidate_id,
            )
        )
        return result.scalar_one_or_none()
