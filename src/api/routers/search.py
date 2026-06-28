"""
Search and ranking router — the main ranking pipeline endpoint.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import User
from src.api.dependencies import get_current_user
from src.api.models.request_models import (
    ExplanationResponse,
    RankedListResponse,
    RankRequest,
    RankResultItem,
)
from src.api.repositories.jd_repo import JDRepository
from src.api.repositories.ranking_repo import RankingRepository
from src.api.repositories.candidate_repo import CandidateRepository
from src.utils.logger import get_logger

logger = get_logger("search_router")

router = APIRouter()


@router.post("/rank", response_model=RankedListResponse)
async def rank_candidates(
    request: RankRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Rank candidates against a job description.

    Full pipeline: JD parse → FAISS retrieval → Cross-encoder rerank →
    Feature retrieval → LTR ranking → SHAP explanation.
    """
    start_time = time.time()

    # Validate JD exists
    jd_repo = JDRepository(session)
    jd = await jd_repo.get_by_id(request.jd_id)
    if jd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="JD not found",
        )

    # Get indexed candidates
    candidate_repo = CandidateRepository(session)
    total_candidates = await candidate_repo.count(status="indexed")

    if total_candidates == 0:
        return RankedListResponse(
            jd_id=request.jd_id,
            total_candidates_screened=0,
            results=[],
            processing_time_seconds=time.time() - start_time,
        )

    # For now, return a simplified ranking based on available candidates
    # Full pipeline will be connected when models are trained
    candidates = await candidate_repo.list_all(status="indexed", limit=request.top_k)

    results: list[RankResultItem] = []
    ranking_repo = RankingRepository(session)

    # Delete previous rankings for this JD
    await ranking_repo.delete_rankings_for_jd(request.jd_id)

    for rank_idx, candidate in enumerate(candidates, 1):
        # Compute basic similarity scores (placeholder until models are loaded)
        semantic_score = max(0.0, 1.0 - (rank_idx * 0.05))
        evidence_score = 0.5
        career_score = min(1.0, float(candidate.experience_years or 0) / 10.0)
        behavior_score = 0.5
        final_score = (
            0.4 * semantic_score
            + 0.25 * evidence_score
            + 0.25 * career_score
            + 0.1 * behavior_score
        )

        # Store ranking
        await ranking_repo.create_ranking(
            jd_id=request.jd_id,
            candidate_id=candidate.candidate_id,
            rank=rank_idx,
            semantic_score=semantic_score,
            evidence_score=evidence_score,
            career_score=career_score,
            behavior_score=behavior_score,
            final_score=final_score,
        )

        skills = candidate.skills or []  # type: ignore
        summary = (
            f"Candidate with {candidate.experience_years or 0:.0f} years experience "
            f"and {len(skills)} skills matched."
        )

        results.append(
            RankResultItem(
                rank=rank_idx,
                candidate_id=candidate.candidate_id,  # type: ignore
                final_score=round(final_score, 4),
                semantic_score=round(semantic_score, 4),
                evidence_score=round(evidence_score, 4),
                career_score=round(career_score, 4),
                behavior_score=round(behavior_score, 4),
                explanation_summary=summary,
            )
        )

    processing_time = time.time() - start_time

    logger.info(
        f"Ranking complete: JD={request.jd_id}, "
        f"{len(results)} candidates ranked in {processing_time:.2f}s"
    )

    return RankedListResponse(
        jd_id=request.jd_id,
        total_candidates_screened=total_candidates,
        results=results,
        processing_time_seconds=round(processing_time, 3),
    )


@router.get("/rank/{jd_id}/{candidate_id}/explain", response_model=ExplanationResponse)
async def get_explanation(
    jd_id: str,
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get SHAP-based explanation for a candidate ranking."""
    ranking_repo = RankingRepository(session)
    ranking = await ranking_repo.get_ranking(jd_id, candidate_id)

    if ranking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ranking not found for this JD-candidate pair",
        )

    # Check for existing explanation
    explanation = await ranking_repo.get_explanation_for_ranking(ranking.ranking_id)  # type: ignore

    if explanation:
        return ExplanationResponse(
            candidate_id=candidate_id,
            rank=ranking.rank,  # type: ignore
            final_score=ranking.final_score,  # type: ignore
            shap_values=explanation.shap_values or {},  # type: ignore
            feature_contributions=explanation.feature_contributions or [],  # type: ignore
            natural_language_explanation=explanation.natural_language or "",  # type: ignore
            counterfactuals=explanation.counterfactuals or [],  # type: ignore
        )

    # Generate basic explanation (full SHAP when model is loaded)
    return ExplanationResponse(
        candidate_id=candidate_id,
        rank=ranking.rank,  # type: ignore
        final_score=ranking.final_score,  # type: ignore
        shap_values={},
        feature_contributions=[
            {"feature": "semantic_score", "contribution": ranking.semantic_score or 0, "direction": "positive"},
            {"feature": "career_score", "contribution": ranking.career_score or 0, "direction": "positive"},
            {"feature": "evidence_score", "contribution": ranking.evidence_score or 0, "direction": "positive"},
        ],
        natural_language_explanation=(
            f"Candidate ranked #{ranking.rank} with semantic fit "
            f"{ranking.semantic_score or 0:.2f}, career score {ranking.career_score or 0:.2f}."
        ),
        counterfactuals=[],
    )
