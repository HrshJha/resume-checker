"""
SHAP explainability for candidate ranking decisions.

Uses TreeSHAP for XGBoost/LightGBM models to compute per-feature
contributions. Generates natural language explanations and counterfactuals.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("shap_explainer")


class SHAPExplainer:
    """TreeSHAP-based explainability for LTR models."""

    def __init__(self, model: Any, feature_names: list[str]) -> None:
        """
        Initialize SHAP explainer.

        Args:
            model: Trained XGBoost or LightGBM model object.
            feature_names: List of feature names matching model features.
        """
        import shap

        self.feature_names = feature_names
        self.explainer = shap.TreeExplainer(model)
        self._global_importance: Optional[dict[str, float]] = None
        logger.info(f"SHAP TreeExplainer initialized with {len(feature_names)} features")

    def explain_candidate(
        self, feature_vector: np.ndarray
    ) -> dict[str, Any]:
        """
        Compute SHAP values for a single candidate.

        Args:
            feature_vector: 1D feature array of shape (n_features,).

        Returns:
            Dict with shap_values, feature_contributions, and top features.
        """
        X = feature_vector.reshape(1, -1)
        shap_values = self.explainer.shap_values(X)

        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        values = shap_values[0]

        # Build feature contributions
        contributions: list[dict[str, Any]] = []
        for i, (name, value) in enumerate(zip(self.feature_names, values)):
            contributions.append({
                "feature": name,
                "shap_value": float(value),
                "feature_value": float(feature_vector[i]),
                "direction": "positive" if value > 0 else "negative",
                "magnitude": abs(float(value)),
            })

        # Sort by magnitude
        contributions.sort(key=lambda x: x["magnitude"], reverse=True)

        # SHAP values as dict
        shap_dict = {
            name: float(val) for name, val in zip(self.feature_names, values)
        }

        return {
            "shap_values": shap_dict,
            "feature_contributions": contributions,
            "top_positive": [c for c in contributions[:10] if c["direction"] == "positive"],
            "top_negative": [c for c in contributions[:10] if c["direction"] == "negative"],
            "base_value": float(self.explainer.expected_value) if isinstance(self.explainer.expected_value, (int, float)) else float(self.explainer.expected_value[0]),
        }

    def explain_batch(
        self, feature_matrix: np.ndarray
    ) -> list[dict[str, Any]]:
        """Compute SHAP values for a batch of candidates."""
        shap_values = self.explainer.shap_values(feature_matrix)

        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        results = []
        for i in range(feature_matrix.shape[0]):
            values = shap_values[i]
            contributions = []
            for j, (name, val) in enumerate(zip(self.feature_names, values)):
                contributions.append({
                    "feature": name,
                    "shap_value": float(val),
                    "feature_value": float(feature_matrix[i, j]),
                    "direction": "positive" if val > 0 else "negative",
                    "magnitude": abs(float(val)),
                })
            contributions.sort(key=lambda x: x["magnitude"], reverse=True)  # type: ignore

            results.append({
                "shap_values": {name: float(val) for name, val in zip(self.feature_names, values)},
                "feature_contributions": contributions,
            })

        logger.debug(f"SHAP explained {len(results)} candidates")
        return results

    def global_feature_importance(
        self, feature_matrix: np.ndarray
    ) -> dict[str, float]:
        """Compute global feature importance via mean |SHAP|."""
        if self._global_importance is not None:
            return self._global_importance

        shap_values = self.explainer.shap_values(feature_matrix)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        mean_abs = np.abs(shap_values).mean(axis=0)

        self._global_importance = {
            name: float(val) for name, val in zip(self.feature_names, mean_abs)
        }
        return self._global_importance


def generate_nl_explanation(
    contributions: list[dict],
    rank: int,
    final_score: float,
) -> str:
    """
    Generate a natural language explanation from SHAP contributions.

    Args:
        contributions: Sorted feature contributions list.
        rank: Candidate rank.
        final_score: Final ranking score.

    Returns:
        Natural language explanation string.
    """
    top_positive = [c for c in contributions[:5] if c["direction"] == "positive"]
    top_negative = [c for c in contributions[:5] if c["direction"] == "negative"]

    parts = [f"This candidate is ranked #{rank} with a score of {final_score:.3f}."]

    if top_positive:
        strengths = []
        for c in top_positive[:3]:
            feature = c["feature"].replace("_", " ").replace("sem ", "semantic ").replace("car ", "career ")
            strengths.append(feature)
        parts.append(f"Key strengths: {', '.join(strengths)}.")

    if top_negative:
        gaps = []
        for c in top_negative[:2]:
            feature = c["feature"].replace("_", " ")
            gaps.append(feature)
        parts.append(f"Areas for improvement: {', '.join(gaps)}.")

    return " ".join(parts)


def generate_counterfactuals(
    contributions: list[dict],
    current_rank: int,
    top_k: int = 3,
) -> list[dict]:
    """
    Generate counterfactual explanations.

    Identifies which feature changes would most improve the ranking.

    Args:
        contributions: Sorted feature contributions.
        current_rank: Current candidate rank.
        top_k: Number of counterfactuals to generate.

    Returns:
        List of counterfactual dicts with change description and impact.
    """
    counterfactuals = []

    # Look at top negative contributions — improving these would help most
    negative = [c for c in contributions if c["direction"] == "negative"]

    for c in negative[:top_k]:
        feature = c["feature"].replace("_", " ")
        magnitude = c["magnitude"]

        cf = {
            "feature": c["feature"],
            "change": f"Improving '{feature}' could boost ranking",
            "estimated_impact": f"Potential rank improvement: ~{max(1, int(magnitude * 10))} positions",
            "current_value": c["feature_value"],
            "shap_impact": c["shap_value"],
        }
        counterfactuals.append(cf)

    return counterfactuals
