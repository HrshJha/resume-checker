"""
Evidence validator module.

Validates whether claimed skills are backed by actual experience,
projects, or certifications to generate an 'evidence score'.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

logger = get_logger("evidence_validator")


class EvidenceValidator:
    """Validates claimed skills against work history and projects."""

    def __init__(self) -> None:
        pass

    def validate_skills(
        self,
        candidate_skills: list[str],
        experience: list[dict],
        projects: list[dict],
        certifications: list[dict],
    ) -> dict[str, Any]:
        """
        Validate skills against evidence sources.

        Args:
            candidate_skills: List of extracted candidate skills.
            experience: Parsed experience entries.
            projects: Parsed project entries.
            certifications: Parsed certifications.

        Returns:
            Dict containing evidence scores and breakdowns.
        """
        if not candidate_skills:
            return {"overall_evidence_score": 0.0, "backed_ratio": 0.0}

        backed_skills: set[str] = set()
        evidence_points = 0.0

        cand_skills_lower = {s.lower(): s for s in candidate_skills}

        # Check Experience
        for exp in experience:
            duration = exp.get("duration_months", 0)
            weight = min(1.0, duration / 12.0) if duration else 0.5

            # Search in tech stack and bullets
            tech_lower = [t.lower() for t in exp.get("technologies", [])]
            bullets_text = " ".join(exp.get("bullets", [])).lower()

            for s_lower, s_orig in cand_skills_lower.items():
                if s_lower in tech_lower or s_lower in bullets_text:
                    backed_skills.add(s_orig)
                    evidence_points += (1.0 * weight)

        # Check Projects
        for proj in projects:
            weight = proj.get("complexity_score", 5.0) / 10.0
            tech_lower = [t.lower() for t in proj.get("technologies", [])]
            desc_text = proj.get("description", "").lower()

            for s_lower, s_orig in cand_skills_lower.items():
                if s_lower in tech_lower or s_lower in desc_text:
                    backed_skills.add(s_orig)
                    evidence_points += (0.8 * weight)

        # Check Certifications
        for cert in certifications:
            cert_name = cert.get("name", "").lower()
            for s_lower, s_orig in cand_skills_lower.items():
                if s_lower in cert_name:
                    backed_skills.add(s_orig)
                    evidence_points += 1.0

        # Calculate scores
        backed_ratio = len(backed_skills) / len(candidate_skills)

        # Max evidence points = num skills * 2
        max_possible_points = len(candidate_skills) * 2.0
        overall_score = min(evidence_points / max_possible_points, 1.0) if max_possible_points > 0 else 0.0

        logger.debug(
            f"Evidence validation: {len(backed_skills)}/{len(candidate_skills)} backed, "
            f"score={overall_score:.2f}"
        )

        return {
            "overall_evidence_score": overall_score,
            "backed_ratio": backed_ratio,
            "backed_skills_count": len(backed_skills),
            "unbacked_skills_count": len(candidate_skills) - len(backed_skills),
        }

    def compute_jd_evidence_score(
        self,
        required_skills: list[str],
        candidate_skills: list[str],
        evidence_result: dict[str, Any],
    ) -> float:
        """
        Compute a specialized evidence score for the JD's required skills.
        If the candidate has the required skill AND it's backed by evidence,
        they get full points.
        """
        req_lower = {s.lower() for s in required_skills}
        cand_lower = {s.lower() for s in candidate_skills}

        if not req_lower:
            return 1.0

        # This is a simplification. For full accuracy, we should track exactly
        # which skills are backed. We'll use the overall backed_ratio as a proxy
        # penalty if we don't have the granular mapping.

        exact_matches = req_lower.intersection(cand_lower)
        base_match = len(exact_matches) / len(req_lower)

        backed_ratio = evidence_result.get("backed_ratio", 0.0)

        # The score is a combination of having the skill and having general evidence
        jd_evidence = base_match * (0.5 + (0.5 * backed_ratio))

        return min(jd_evidence, 1.0)
