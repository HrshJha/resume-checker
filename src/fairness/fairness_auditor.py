"""
Fairness auditor.

Analyzes the top-ranked candidates to ensure the model isn't exhibiting
proxy biases (e.g., heavily punishing gap years or correlating strictly with total experience/age).
Since demographic data is masked by default, audits focus on structural fairness.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from typing import Any

from src.utils.logger import get_logger

logger = get_logger("fairness_auditor")


class FairnessAuditor:
    """Audits ranking results for potential structural biases."""

    def __init__(self) -> None:
        # Correlation thresholds above which we flag a potential bias warning
        self.ageism_proxy_threshold = 0.85  # highly correlated with total_years

    def audit_ranking(
        self,
        final_scores: list[float],
        features_list: list[dict[str, float]],
    ) -> dict[str, Any]:
        """
        Audit the ranked list for proxy biases.

        Args:
            final_scores: List of final ranking scores.
            features_list: List of corresponding feature dictionaries.

        Returns:
            Dictionary containing audit results and warnings.
        """
        if not final_scores or len(final_scores) < 2:
            return {"status": "passed", "warnings": []}

        warnings = []
        audit_metrics = {}

        scores_arr = np.array(final_scores)

        # 1. Ageism/Experience Proxy Bias Check
        # Does the model just rank strictly by total years of experience?
        total_years = np.array([f.get("total_years", 0.0) for f in features_list])

        if len(set(total_years)) > 1:
            correlation, p_value = stats.pearsonr(scores_arr, total_years)
            audit_metrics["experience_correlation"] = float(correlation)

            if correlation > self.ageism_proxy_threshold:
                warnings.append(
                    f"High correlation ({correlation:.2f}) between ranking and total years of experience. "
                    "Warning: Potential ageism proxy bias. Check feature importance."
                )
        else:
            audit_metrics["experience_correlation"] = 0.0

        # 2. Stability / Gap Year Punishment Check
        stability_scores = np.array([f.get("stability_score", 0.0) for f in features_list])
        if len(set(stability_scores)) > 1:
            correlation, p_value = stats.pearsonr(scores_arr, stability_scores)
            audit_metrics["stability_correlation"] = float(correlation)

            if correlation > 0.80:
                warnings.append(
                    "High correlation between ranking and career stability. "
                    "Warning: Model may be aggressively punishing gap years or job hopping."
                )
        else:
            audit_metrics["stability_correlation"] = 0.0

        status = "warning" if warnings else "passed"

        logger.info(f"Fairness audit complete: status={status}, {len(warnings)} warnings found.")

        return {
            "status": status,
            "warnings": warnings,
            "metrics": audit_metrics,
        }
