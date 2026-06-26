"""
Career trajectory analyzer.

Calculates metrics like job hopping frequency, average tenure,
promotion velocity, and seniority progression.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

logger = get_logger("career_analyzer")


class CareerAnalyzer:
    """Analyzes a candidate's career progression and stability."""

    def __init__(self) -> None:
        # Keywords suggesting promotion/seniority
        self.senior_keywords = ["senior", "lead", "principal", "staff", "manager", "director", "head", "vp"]
        self.junior_keywords = ["junior", "associate", "intern", "trainee", "assistant"]

    def analyze(self, experience: list[dict], jd_seniority_level: int = 2) -> dict[str, Any]:
        """
        Analyze career trajectory from experience entries.

        Args:
            experience: List of parsed experience entries (ordered newest to oldest).
            jd_seniority_level: Required seniority level (0-6).

        Returns:
            Dict containing career metrics.
        """
        if not experience:
            return {
                "total_years": 0.0,
                "avg_tenure_years": 0.0,
                "job_hops": 0,
                "promotion_velocity": 0.0,
                "seniority_match_score": 0.0 if jd_seniority_level > 0 else 1.0,
                "stability_score": 0.0,
            }

        total_months = 0.0
        company_tenures: dict[str, float] = {}
        promotions = 0

        # Sort chronological (oldest to newest) to detect promotions
        try:
            # Simple assumption: entries are typically newest-first, so reverse them
            exp_chrono = list(reversed(experience))
        except Exception:
            exp_chrono = experience

        prev_role_level = -1

        for exp in exp_chrono:
            duration = exp.get("duration_months", 0.0)
            total_months += duration
            company = exp.get("company", "Unknown").lower()

            if company not in company_tenures:
                company_tenures[company] = 0.0
            company_tenures[company] += duration

            # Estimate role level
            role = exp.get("role", "").lower()
            level = 2 # Mid-level default
            if any(k in role for k in self.senior_keywords):
                level = 3
            elif any(k in role for k in self.junior_keywords):
                level = 1

            if prev_role_level != -1 and level > prev_role_level:
                promotions += 1

            prev_role_level = level

        total_years = total_months / 12.0
        num_companies = len(company_tenures)

        avg_tenure = (total_years / num_companies) if num_companies > 0 else 0.0
        job_hops = max(0, num_companies - 1)

        # Stability score: penalize avg tenure < 1.5 years heavily
        stability_score = min(1.0, avg_tenure / 3.0)

        # Promotion velocity: promotions per year
        promo_velocity = (promotions / total_years) if total_years > 0 else 0.0

        # Seniority Match Score against JD
        cand_highest_level = prev_role_level  # (most recent role is last in chrono)
        if cand_highest_level >= jd_seniority_level:
            seniority_match = 1.0
        elif cand_highest_level == jd_seniority_level - 1:
            seniority_match = 0.7  # Ready for step up
        else:
            seniority_match = 0.3  # Too junior

        # Career progression score (weighted composite)
        career_score = (
            0.4 * stability_score +
            0.4 * seniority_match +
            0.2 * min(1.0, promo_velocity * 2.0)
        )

        logger.debug(
            f"Career analysis: {total_years:.1f}y total, avg tenure {avg_tenure:.1f}y, "
            f"stability {stability_score:.2f}, match {seniority_match:.2f}"
        )

        return {
            "total_years": total_years,
            "avg_tenure_years": avg_tenure,
            "job_hops": job_hops,
            "promotions_detected": promotions,
            "promotion_velocity": promo_velocity,
            "stability_score": stability_score,
            "seniority_match_score": seniority_match,
            "career_score": min(career_score, 1.0),
        }
