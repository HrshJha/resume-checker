"""
Export service — assembles ranking export rows from the database.

Responsibility:
    - Query rankings, candidates, and explanations via existing repositories.
    - Assemble one ``RankingExportRow`` per ranked candidate.
    - Produce a deterministic, rank-ordered list suitable for the formatter.

This service contains NO formatting logic and NO openpyxl imports.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db_models import Candidate, Explanation, JobDescription, Ranking
from src.api.models.export_models import (
    RankingExportRow,
    score_to_confidence,
    score_to_recommendation,
)
from src.api.repositories.candidate_repo import CandidateRepository
from src.api.repositories.jd_repo import JDRepository
from src.api.repositories.ranking_repo import RankingRepository
from src.utils.logger import get_logger

logger = get_logger("export_service")


# ---------------------------------------------------------------------------
# Internal helpers — all pure functions for testability
# ---------------------------------------------------------------------------

def _extract_candidate_name(candidate: Candidate) -> str:
    """
    Extract the candidate's full name from parsed_data.

    Search order:
    1. parsed_data["full_name"]
    2. parsed_data["name"]
    3. First non-empty line of parsed_data["full_text"] (trimmed)
    4. Fallback: candidate_id string
    """
    parsed: dict[str, Any] = candidate.parsed_data or {}  # type: ignore[assignment]

    # Direct keys written by some parsers
    for key in ("full_name", "name"):
        val = parsed.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()

    # First meaningful line of the full text
    full_text: str = parsed.get("full_text", "") or ""
    for line in full_text.splitlines():
        stripped = line.strip()
        # Skip lines that look like email / phone / URL rather than a name
        if (
            stripped
            and len(stripped.split()) >= 2
            and "@" not in stripped
            and "http" not in stripped.lower()
            and len(stripped) < 80
        ):
            return stripped

    return str(candidate.candidate_id)


def _extract_education_summary(candidate: Candidate) -> str:
    """
    Produce a single human-readable string for the highest education entry.

    Returns an empty string when no education data is present.
    """
    education: list[dict[str, Any]] = candidate.education or []  # type: ignore[assignment]
    if not education:
        return ""

    # Take the first entry (parsers typically order by recency / highest level)
    entry: dict[str, Any] = education[0] if isinstance(education, list) else {}

    parts: list[str] = []
    if degree := entry.get("degree", "") or entry.get("qualification", ""):
        parts.append(str(degree).strip())
    if major := entry.get("field_of_study", "") or entry.get("major", ""):
        parts.append(str(major).strip())
    if institution := entry.get("institution", "") or entry.get("university", ""):
        parts.append(str(institution).strip())
    if year := entry.get("end_year", "") or entry.get("graduation_year", ""):
        parts.append(f"({year})")

    return ", ".join(filter(None, parts))


def _format_skills_list(skills: list[Any]) -> str:
    """Convert a skills list to a comma-separated string, max 200 chars."""
    if not skills:
        return ""
    joined = ", ".join(str(s).strip() for s in skills if s)
    return joined[:200] if len(joined) > 200 else joined


def _build_inline_explanation(ranking: Ranking) -> str:
    """
    Build a concise natural-language explanation from ranking sub-scores when
    no Explanation record exists in the database.

    This mirrors the logic in ``search.py:get_explanation()`` but is phrased
    for a recruiter audience reading a spreadsheet cell.
    """
    sem = float(ranking.semantic_score or 0.0) * 100
    car = float(ranking.career_score or 0.0) * 100
    bm25 = float(ranking.behavior_score or 0.0) * 100
    ev = float(ranking.evidence_score or 0.0) * 100
    final = float(ranking.final_score or 0.0) * 100

    rec = score_to_recommendation(float(ranking.final_score or 0.0))

    return (
        f"Ranked #{ranking.rank} | Final: {final:.1f}%. "
        f"Skills match: {sem:.1f}% | Experience: {car:.1f}% | "
        f"Evidence (projects+edu): {ev:.1f}% | BM25 relevance: {bm25:.1f}%. "
        f"Recommendation: {rec}."
    )


def _extract_explanation_text(
    explanation: Optional[Explanation],
    ranking: Ranking,
) -> str:
    """
    Return the best-available explanation string for a candidate.

    Priority:
    1. explanation.natural_language (SHAP-generated)
    2. inline explanation built from ranking scores
    """
    if explanation and explanation.natural_language:  # type: ignore[union-attr]
        return str(explanation.natural_language).strip()  # type: ignore[union-attr]
    return _build_inline_explanation(ranking)


def _extract_skill_lists(
    candidate: Candidate,
    jd: JobDescription,
) -> tuple[str, str]:
    """
    Compute matched and missing required skills for export columns.

    We do a simple normalised exact-match here so the export is fast and
    deterministic.  The full semantic match already ran during ranking; its
    results were used to compute semantic_score but are not persisted per-skill.
    We re-derive them here for the spreadsheet because the ranking phase does
    not store the per-skill breakdown.
    """
    import re

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9+#.]+", " ", s.lower()).strip()

    required: list[str] = jd.required_skills or []  # type: ignore[assignment]
    candidate_skills: list[str] = candidate.skills or []  # type: ignore[assignment]

    if not required:
        return _format_skills_list(candidate_skills), ""

    cand_norm = {_norm(s): s for s in candidate_skills if s}

    matched: list[str] = []
    missing: list[str] = []

    for skill in required:
        norm = _norm(skill)
        if not norm:
            continue
        if norm in cand_norm:
            matched.append(cand_norm[norm])
        else:
            missing.append(skill)

    return _format_skills_list(matched), _format_skills_list(missing)


# ---------------------------------------------------------------------------
# ExportService
# ---------------------------------------------------------------------------

class ExportService:
    """
    Assembles ``RankingExportRow`` instances from the database.

    Uses only existing repositories — no direct ORM queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ranking_repo = RankingRepository(session)
        self._candidate_repo = CandidateRepository(session)
        self._jd_repo = JDRepository(session)

    async def build_ranking_rows(
        self,
        jd_id: str,
        top_k: int = 100,
    ) -> list[RankingExportRow]:
        """
        Build a ranked list of export rows for a given job description.

        Args:
            jd_id:  UUID of the job description to export.
            top_k:  Maximum number of candidates to include.

        Returns:
            List of ``RankingExportRow`` sorted by rank ascending (rank 1 first).

        Raises:
            ValueError: If the JD does not exist or has no rankings yet.
        """
        # ── Validate JD exists ────────────────────────────────────────────
        jd = await self._jd_repo.get_by_id(jd_id)
        if jd is None:
            raise ValueError(f"Job description not found: {jd_id}")

        # ── Fetch rankings (already ordered by rank ASC) ──────────────────
        rankings: list[Ranking] = await self._ranking_repo.get_rankings_for_jd(
            jd_id=jd_id,
            top_k=top_k,
        )

        if not rankings:
            raise ValueError(
                f"No rankings found for JD {jd_id}. "
                "Run POST /api/v1/search/rank first."
            )

        logger.info(
            f"Building export rows for JD={jd_id}: "
            f"{len(rankings)} rankings, top_k={top_k}"
        )

        # ── Batch-fetch candidates ────────────────────────────────────────
        candidate_ids: list[str] = [
            str(r.candidate_id) for r in rankings  # type: ignore[arg-type]
        ]
        candidates: list[Candidate] = await self._candidate_repo.get_by_ids(
            candidate_ids
        )
        candidate_map: dict[str, Candidate] = {
            str(c.candidate_id): c for c in candidates
        }

        # ── Batch-fetch explanations ──────────────────────────────────────
        explanation_map: dict[str, Explanation] = {}
        for ranking in rankings:
            exp = await self._ranking_repo.get_explanation_for_ranking(
                str(ranking.ranking_id)  # type: ignore[arg-type]
            )
            if exp is not None:
                explanation_map[str(ranking.ranking_id)] = exp  # type: ignore[arg-type]

        # ── Assemble rows ─────────────────────────────────────────────────
        export_timestamp = datetime.now(timezone.utc)
        rows: list[RankingExportRow] = []

        for ranking in rankings:
            candidate_id_str = str(ranking.candidate_id)  # type: ignore[arg-type]
            candidate = candidate_map.get(candidate_id_str)

            if candidate is None:
                logger.warning(
                    f"Candidate {candidate_id_str} not found in DB, "
                    "skipping export row"
                )
                continue

            ranking_id_str = str(ranking.ranking_id)  # type: ignore[arg-type]
            explanation = explanation_map.get(ranking_id_str)

            final_score = float(ranking.final_score or 0.0)
            semantic_score = float(ranking.semantic_score or 0.0)
            evidence_score = float(ranking.evidence_score or 0.0)
            career_score = float(ranking.career_score or 0.0)
            behavior_score = float(ranking.behavior_score or 0.0)

            matching_skills, missing_skills = _extract_skill_lists(candidate, jd)

            row = RankingExportRow(
                rank=int(ranking.rank),  # type: ignore[arg-type]
                candidate_id=candidate_id_str,
                candidate_name=_extract_candidate_name(candidate),
                job_id=jd_id,
                resume_path=str(candidate.raw_resume_path or ""),
                final_score=round(final_score, 6),
                semantic_score=round(semantic_score, 6),
                evidence_score=round(evidence_score, 6),
                career_score=round(career_score, 6),
                behavior_score=round(behavior_score, 6),
                model_score=round(final_score, 6),   # mirrors final_score (see plan)
                confidence=score_to_confidence(final_score),
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                years_experience=float(candidate.experience_years or 0.0),
                education=_extract_education_summary(candidate),
                recommendation=score_to_recommendation(final_score),
                explanation=_extract_explanation_text(explanation, ranking),
                timestamp=export_timestamp,
            )
            rows.append(row)

        # Guarantee ascending rank order regardless of DB retrieval order
        rows.sort(key=lambda r: r.rank)

        logger.info(
            f"Export assembled: {len(rows)} rows for JD={jd_id}"
        )
        return rows
