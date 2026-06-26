"""
Feature engineering pipeline — creates the 255-dimension vector for LTR.

Combines signals from JD, retrieval, skill graph, evidence, career,
and behavior modules into a flat float vector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from src.behavior.behavioral_extractor import BehavioralExtractor
from src.career.career_analyzer import CareerAnalyzer
from src.evidence.evidence_validator import EvidenceValidator
from src.graph.skill_graph import SkillGraph
from src.utils.logger import get_logger

logger = get_logger("feature_engineer")


class FeatureEngineer:
    """Master pipeline to build the LTR feature vector."""

    def __init__(self, feature_config_path: str = "./configs/feature_config.json") -> None:
        self.config_path = Path(feature_config_path)
        self.feature_names: list[str] = []
        self._load_config()

        self.skill_graph = SkillGraph()
        self.evidence_validator = EvidenceValidator()
        self.career_analyzer = CareerAnalyzer()
        self.behavioral_extractor = BehavioralExtractor()

    def _load_config(self) -> None:
        """Load feature names from config."""
        if not self.config_path.exists():
            logger.warning(f"Feature config not found at {self.config_path}, using defaults")
            # Fallback to minimal set for testing
            self.feature_names = [
                "dense_score", "bm25_score", "cross_encoder_score",
                "exact_match_ratio", "category_match_ratio",
                "evidence_score", "total_years", "stability_score",
                "seniority_match", "leadership_score", "impact_score",
                "behavior_score", "career_score",
            ]
            return

        try:
            with open(self.config_path) as f:
                config = json.load(f)

            names = []
            for group in config.get("feature_groups", []):
                for feature in group.get("features", []):
                    names.append(feature["name"])

            self.feature_names = names
            logger.info(f"Loaded {len(self.feature_names)} features from config")
        except Exception as e:
            logger.error(f"Failed to load feature config: {e}")
            self.feature_names = ["fallback_score"]

    def build_features(
        self,
        jd_data: dict[str, Any],
        candidate_data: dict[str, Any],
        retrieval_scores: dict[str, float],
    ) -> dict[str, float]:
        """
        Build the full feature dictionary for a (JD, Candidate) pair.

        Args:
            jd_data: Parsed JD intelligence.
            candidate_data: Parsed candidate intelligence.
            retrieval_scores: Scores from Phase 3 (dense, bm25, cross_encoder).

        Returns:
            Dictionary mapping feature name to float value.
        """
        features: dict[str, float] = {}

        # 1. Retrieval Features
        features["dense_score"] = retrieval_scores.get("dense_score", 0.0)
        features["bm25_score"] = retrieval_scores.get("bm25_score", 0.0)
        features["cross_encoder_score"] = retrieval_scores.get("cross_encoder_score", 0.0)

        # 2. Skill Overlap Features
        req_skills = jd_data.get("required_skills", [])
        cand_skills = candidate_data.get("skills", [])
        overlap = self.skill_graph.compute_overlap(req_skills, cand_skills)
        features["exact_match_ratio"] = overlap["exact_match_ratio"]
        features["category_match_ratio"] = overlap["category_match_ratio"]

        # 3. Evidence Features
        experience = candidate_data.get("experience", [])
        projects = candidate_data.get("projects", [])
        certifications = candidate_data.get("certifications", [])

        evidence = self.evidence_validator.validate_skills(
            cand_skills, experience, projects, certifications
        )
        features["evidence_score"] = evidence["overall_evidence_score"]
        features["backed_ratio"] = evidence["backed_ratio"]

        # 4. Career Features
        jd_seniority = jd_data.get("seniority", 2)
        career = self.career_analyzer.analyze(experience, jd_seniority)
        features["total_years"] = career["total_years"]
        features["avg_tenure_years"] = career["avg_tenure_years"]
        features["stability_score"] = career["stability_score"]
        features["seniority_match"] = career["seniority_match_score"]
        features["career_score"] = career["career_score"]

        # 5. Behavior Features
        full_text = candidate_data.get("full_text", "")
        behavior = self.behavioral_extractor.extract_signals(full_text, experience, projects)
        features["leadership_score"] = behavior["leadership_score"]
        features["ownership_score"] = behavior["ownership_score"]
        features["impact_score"] = behavior["impact_score"]
        features["learning_score"] = behavior["learning_score"]
        features["behavior_score"] = behavior["behavior_score"]

        # Ensure all defined features exist
        final_vector: dict[str, float] = {}
        for fname in self.feature_names:
            final_vector[fname] = features.get(fname, 0.0)

        return final_vector

    def vectorize(self, feature_dict: dict[str, float]) -> np.ndarray:
        """Convert feature dictionary to numpy array matching config order."""
        vector = [feature_dict.get(fname, 0.0) for fname in self.feature_names]
        return np.array(vector, dtype=np.float32)
