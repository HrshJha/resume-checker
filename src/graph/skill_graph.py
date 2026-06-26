"""
Skill graph module — builds and queries the technology ontology.

Maps candidate skills to JD requirements, accounting for categories
and related technologies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("skill_graph")


class SkillGraph:
    """In-memory skill ontology and relationship graph."""

    def __init__(self, ontology_path: str = "./src/graph/ontology_data/tech_ontology.json") -> None:
        self.ontology_path = Path(ontology_path)
        self.categories: dict[str, list[dict]] = {}
        self.skill_to_category: dict[str, str] = {}
        self._load_ontology()

    def _load_ontology(self) -> None:
        """Load skill ontology from JSON."""
        if not self.ontology_path.exists():
            logger.warning(f"Ontology file not found: {self.ontology_path}")
            return

        try:
            with open(self.ontology_path) as f:
                self.categories = json.load(f)

            for category, skills in self.categories.items():
                for skill_dict in skills:
                    name = skill_dict["name"].lower()
                    self.skill_to_category[name] = category
                    for alias in skill_dict.get("aliases", []):
                        self.skill_to_category[alias.lower()] = category

            logger.info(f"Loaded skill ontology with {len(self.categories)} categories")
        except Exception as e:
            logger.error(f"Failed to load ontology: {e}")

    def get_category(self, skill: str) -> str:
        """Get the category for a skill."""
        return self.skill_to_category.get(skill.lower(), "unknown")

    def are_related(self, skill1: str, skill2: str) -> bool:
        """Check if two skills belong to the same category."""
        cat1 = self.get_category(skill1)
        cat2 = self.get_category(skill2)
        if cat1 == "unknown" or cat2 == "unknown":
            return False
        return cat1 == cat2

    def compute_overlap(
        self,
        required_skills: list[str],
        candidate_skills: list[str],
    ) -> dict[str, Any]:
        """
        Compute the overlap and coverage between required and candidate skills.

        Args:
            required_skills: List of skills required by JD.
            candidate_skills: List of skills possessed by candidate.

        Returns:
            Dict containing match metrics.
        """
        req_lower = {s.lower() for s in required_skills}
        cand_lower = {s.lower() for s in candidate_skills}

        if not req_lower:
            return {
                "exact_match_ratio": 1.0,
                "category_match_ratio": 1.0,
                "missing_skills": [],
                "matched_skills": list(cand_lower),
            }

        exact_matches = req_lower.intersection(cand_lower)
        exact_match_ratio = len(exact_matches) / len(req_lower)

        # Check category-level matches for missing skills
        missing_exact = req_lower - exact_matches
        category_matches = set()

        cand_categories = {self.get_category(s) for s in cand_lower}

        for missing in missing_exact:
            cat = self.get_category(missing)
            if cat != "unknown" and cat in cand_categories:
                category_matches.add(missing)

        total_coverage = (len(exact_matches) + (len(category_matches) * 0.5)) / len(req_lower)

        return {
            "exact_match_ratio": min(exact_match_ratio, 1.0),
            "category_match_ratio": min(total_coverage, 1.0),
            "missing_skills": list(missing_exact - category_matches),
            "matched_skills": list(exact_matches),
            "related_skills": list(category_matches),
        }
