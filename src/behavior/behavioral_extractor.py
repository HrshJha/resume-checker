"""
Behavioral and impact signal extractor.

Analyzes resume text to detect leadership, ownership, quantifiable
impact, and continuous learning signals.
"""

from __future__ import annotations

import re
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("behavioral_extractor")


class BehavioralExtractor:
    """Extracts soft skills and behavioral signals."""

    def __init__(self) -> None:
        self.leadership_keywords = [
            "led", "managed", "directed", "mentored", "coached", "spearheaded",
            "orchestrated", "founder", "head", "lead", "supervis", "guided",
        ]
        self.ownership_keywords = [
            "owned", "initiated", "founded", "created", "built from scratch",
            "architected", "designed", "established", "drove", "pioneered",
        ]
        self.continuous_learning_keywords = [
            "certified", "certification", "course", "bootcamp", "hackathon",
            "open source", "published", "research", "self-taught",
        ]
        # Regex for numbers with % or $ or 'users', indicating impact
        self.impact_pattern = re.compile(
            r"(\d+[%$]|[$]\d+|\d+[KkMm]\b|\d+\s*(users|clients|customers|revenue|cost|latency))"
        )

    def extract_signals(
        self,
        full_text: str,
        experience: list[dict],
        projects: list[dict],
    ) -> dict[str, Any]:
        """
        Extract behavioral signals from parsed resume.

        Args:
            full_text: Complete resume text.
            experience: Parsed experience entries.
            projects: Parsed project entries.

        Returns:
            Dict containing behavioral scores.
        """
        text_lower = full_text.lower()

        # 1. Leadership Score
        leadership_count = sum(1 for kw in self.leadership_keywords if kw in text_lower)
        leadership_score = min(1.0, leadership_count / 3.0)

        # 2. Ownership Score
        ownership_count = sum(1 for kw in self.ownership_keywords if kw in text_lower)
        ownership_score = min(1.0, ownership_count / 3.0)

        # 3. Continuous Learning Score
        learning_count = sum(1 for kw in self.continuous_learning_keywords if kw in text_lower)
        learning_score = min(1.0, learning_count / 2.0)

        # 4. Impact Quantifiability Score (how often they use numbers to describe success)
        impact_metrics_count = 0
        total_bullets = 0

        for exp in experience:
            bullets = exp.get("bullets", [])
            total_bullets += len(bullets)
            for bullet in bullets:
                if self.impact_pattern.search(bullet):
                    impact_metrics_count += 1

        for proj in projects:
            desc = proj.get("description", "")
            if desc:
                total_bullets += 1
                if self.impact_pattern.search(desc) or proj.get("impact_metrics"):
                    impact_metrics_count += 1

        impact_score = 0.0
        if total_bullets > 0:
            # If 20% of bullets have metrics, that's excellent
            impact_ratio = impact_metrics_count / total_bullets
            impact_score = min(1.0, impact_ratio / 0.2)

        # Overall behavioral composite
        behavior_score = (
            0.3 * leadership_score +
            0.2 * ownership_score +
            0.3 * impact_score +
            0.2 * learning_score
        )

        logger.debug(
            f"Behavioral analysis: lead={leadership_score:.2f}, own={ownership_score:.2f}, "
            f"impact={impact_score:.2f}, overall={behavior_score:.2f}"
        )

        return {
            "leadership_score": leadership_score,
            "ownership_score": ownership_score,
            "learning_score": learning_score,
            "impact_score": impact_score,
            "behavior_score": min(behavior_score, 1.0),
        }
