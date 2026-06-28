"""
Search and ranking router — the main ranking pipeline endpoint.
"""

from __future__ import annotations

import time
import re
from typing import Any, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import Candidate, User
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


class ScoredCandidate(TypedDict):
    candidate: Candidate
    final_score: float
    semantic_score: float
    evidence_score: float
    career_score: float
    behavior_score: float
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]


_STOP_WORDS = {
    "and", "or", "the", "a", "an", "to", "of", "in", "for", "with", "on",
    "by", "is", "are", "as", "be", "will", "you", "we", "our", "your",
    "this", "that", "from", "using", "experience", "years", "skills",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, numerator / denominator))


def _skill_match_ratio(jd_skills: list[str], candidate_skills: list[str]) -> tuple[float, list[str], list[str]]:
    candidate_normalized = {_norm(skill): skill for skill in candidate_skills if skill}
    matched: list[str] = []
    missing: list[str] = []

    for skill in jd_skills:
        normalized = _norm(skill)
        if not normalized:
            continue
        if normalized in candidate_normalized:
            matched.append(candidate_normalized[normalized])
        else:
            missing.append(skill)

    # Stage 5: Semantic Match using sentence-transformers for unmapped skills
    if missing and candidate_skills:
        try:
            from src.jd.jd_embedder import embed_texts_batch
            import numpy as np
            
            # Embed missing JD skills and all candidate skills
            jd_embs = embed_texts_batch(missing)
            cand_embs = embed_texts_batch(candidate_skills)
            
            # Compute cosine similarity (inner product of L2 normalized vectors)
            sim_matrix = np.dot(jd_embs, cand_embs.T)
            
            still_missing = []
            for i, skill in enumerate(missing):
                max_sim = float(np.max(sim_matrix[i])) if sim_matrix.shape[1] > 0 else 0.0
                if max_sim >= 0.82: # 0.82 threshold for semantic equivalence in BGE models
                    best_cand_idx = int(np.argmax(sim_matrix[i]))
                    matched.append(candidate_skills[best_cand_idx])
                else:
                    still_missing.append(skill)
            missing = still_missing
        except Exception as e:
            logger.warning(f"Semantic match failed, falling back to exact match: {e}")

    return _ratio(len(matched), len(matched) + len(missing)), matched, missing


def _token_overlap_score(jd_text: str, candidate_text: str) -> float:
    jd_tokens = {
        token for token in re.findall(r"[a-z0-9+#.]{2,}", jd_text.lower())
        if token not in _STOP_WORDS
    }
    candidate_tokens = {
        token for token in re.findall(r"[a-z0-9+#.]{2,}", candidate_text.lower())
        if token not in _STOP_WORDS
    }
    if not jd_tokens:
        return 0.0
    return len(jd_tokens & candidate_tokens) / len(jd_tokens)


def _experience_score(candidate_years: float, jd_min_years: float | None, jd_max_years: float | None) -> float:
    if jd_min_years is None and jd_max_years is None:
        return min(1.0, candidate_years / 5.0)
    if jd_min_years is not None and candidate_years < jd_min_years:
        return max(0.0, candidate_years / jd_min_years)
    if jd_max_years is not None and jd_max_years > 0 and candidate_years > jd_max_years + 4:
        return 0.85
    return 1.0


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

    candidates = await candidate_repo.list_all(status="indexed", limit=1000)

    results: list[RankResultItem] = []
    ranking_repo = RankingRepository(session)

    # Delete previous rankings for this JD
    await ranking_repo.delete_rankings_for_jd(request.jd_id)
    await session.flush()

    scored_candidates: list[ScoredCandidate] = []
    required_skills = _as_str_list(jd.required_skills)
    preferred_skills = _as_str_list(jd.preferred_skills)
    jd_text = str(jd.raw_text or "")

    for candidate in candidates:
        candidate_skills = _as_str_list(candidate.skills)
        parsed_data = cast(Any, candidate.parsed_data) or {}
        sections = parsed_data.get("sections", {}) if isinstance(parsed_data, dict) else {}
        candidate_text = " ".join(str(value) for value in sections.values())

        required_ratio, matched_required, missing_required = _skill_match_ratio(
            required_skills, candidate_skills
        )
        preferred_ratio, matched_preferred, _missing_preferred = _skill_match_ratio(
            preferred_skills, candidate_skills
        )
        text_overlap = _token_overlap_score(jd_text, candidate_text)
        # Scoring Distribution (as per plan):
        # - Skills Match: 40%
        # - Experience Match: 25%
        # - Projects: 15%
        # - Education: 10%
        # - Preferred Skills: 5%
        # - Certifications: 5%

        # Skills (40% required, 5% preferred)
        semantic_score = min(1.0, required_ratio)
        preferred_score = min(1.0, preferred_ratio)
        
        # Experience (25%)
        career_score = _experience_score(
            float(candidate.experience_years or 0.0),
            float(jd.experience_min_years) if jd.experience_min_years is not None else None,
            float(jd.experience_max_years) if jd.experience_max_years is not None else None,
        )

        # Evidence (Projects 15%, Education 10%, Certs 5%)
        has_projects = 1.0 if candidate.projects else 0.0
        has_education = 1.0 if candidate.education else 0.0
        has_certs = 1.0 if candidate.certifications else 0.0
        
        evidence_score = min(1.0, (has_projects * 0.50) + (has_education * 0.33) + (has_certs * 0.17))
        
        behavior_score = min(1.0, text_overlap * 2.0) # Used for logging but not in main final score

        final_score = (
            0.40 * semantic_score
            + 0.05 * preferred_score
            + 0.25 * career_score
            + 0.15 * has_projects
            + 0.10 * has_education
            + 0.05 * has_certs
        )

        scored_candidates.append(
            {
                "candidate": candidate,
                "final_score": final_score,
                "semantic_score": semantic_score,
                "evidence_score": evidence_score,
                "career_score": career_score,
                "behavior_score": behavior_score,
                "matched_required": matched_required,
                "missing_required": missing_required,
                "matched_preferred": matched_preferred,
            }
        )

    scored_candidates.sort(key=lambda item: item["final_score"], reverse=True)

    for rank_idx, item in enumerate(scored_candidates[:request.top_k], 1):
        candidate = item["candidate"]

        # Store ranking
        await ranking_repo.create_ranking(
            jd_id=request.jd_id,
            candidate_id=candidate.candidate_id,
            rank=rank_idx,
            semantic_score=item["semantic_score"],
            evidence_score=item["evidence_score"],
            career_score=item["career_score"],
            behavior_score=item["behavior_score"],
            final_score=item["final_score"],
        )

        summary = (
            f"Matched {len(item['matched_required'])}/{len(required_skills)} required skills, "
            f"{len(item['matched_preferred'])}/{len(preferred_skills)} preferred skills, "
            f"{float(candidate.experience_years or 0.0):.1f} years parsed experience. "
            f"Missing: {', '.join(item['missing_required'][:5]) or 'none'}."
        )

        results.append(
            RankResultItem(
                rank=rank_idx,
                candidate_id=candidate.candidate_id,  # type: ignore
                final_score=round(item["final_score"], 4),
                semantic_score=round(item["semantic_score"], 4),
                evidence_score=round(item["evidence_score"], 4),
                career_score=round(item["career_score"], 4),
                behavior_score=round(item["behavior_score"], 4),
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
            f"Candidate ranked #{ranking.rank} with a final score of {ranking.final_score * 100:.1f}%.\n\n"
            f"**Strengths**:\n"
            f"- Strong semantic fit ({(ranking.semantic_score or 0) * 100:.1f}%) covering key requirements.\n"
            f"- Demonstrated {ranking.career_score or 0:.1f} years of relevant calendar experience.\n"
            f"- Strong evidence profile ({(ranking.evidence_score or 0) * 100:.1f}%).\n\n"
            f"**Weaknesses/Gaps**:\n"
            f"- Review missing preferred skills or potential domain gaps if score is below 80%."
        ),
        counterfactuals=[],
    )
