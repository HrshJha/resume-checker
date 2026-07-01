"""
Export data models for the XLSX ranking report.

``RankingExportRow`` is the single source of truth for every column that
appears in the exported spreadsheet.  The export service populates instances
of this class; the Excel formatter consumes them.  Nothing else in the
pipeline needs to know about openpyxl.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RankingExportRow:
    """
    One row in the exported ranking spreadsheet.

    Field order matches the physical column order in the generated XLSX.
    All score fields are in the range [0.0, 1.0] unless noted otherwise.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    rank: int
    """1-based rank position (ascending — rank 1 is the best candidate)."""

    candidate_id: str
    """UUID of the candidate record in the database."""

    candidate_name: str
    """
    Best-effort full name extracted from parsed_data.  Falls back to the
    candidate_id string if the name cannot be recovered from the resume.
    """

    job_id: str
    """UUID of the job description this ranking belongs to."""

    resume_path: str
    """
    Absolute or relative path to the raw resume file on disk.
    Empty string when the file path is not recorded.
    """

    # ── Scores ──────────────────────────────────────────────────────────────
    final_score: float
    """
    Composite ranking score.  Computed as a weighted sum of the sub-scores
    during the search/rank pipeline.  Range: [0.0, 1.0].
    """

    semantic_score: float
    """
    Skill-match ratio (required skills found / required skills total).
    Stored in the ``semantic_score`` column of the rankings table.
    Range: [0.0, 1.0].
    """

    evidence_score: float
    """
    Evidence richness: (has_projects + has_education) / 2.
    Range: [0.0, 1.0].
    """

    career_score: float
    """
    Experience-match score normalised against the JD's required years.
    Range: [0.0, 1.0].
    """

    behavior_score: float
    """
    BM25 relevance score (normalised).  Stored in behavior_score column.
    Range: [0.0, 1.0].
    """

    model_score: float
    """
    Final composite score from the ranking model (mirrors final_score when
    XGBoost LTR is not trained; populated directly from final_score).
    Range: [0.0, 1.0].
    """

    confidence: float
    """
    Confidence level derived from final_score via sigmoid calibration.
    Range: [0.0, 1.0].  Displayed as a percentage in the spreadsheet.
    """

    # ── Skill Analysis ───────────────────────────────────────────────────────
    matching_skills: str
    """
    Comma-separated list of required skills found in the candidate's resume.
    """

    missing_skills: str
    """
    Comma-separated list of required skills NOT found in the candidate's
    resume.
    """

    # ── Candidate Metadata ───────────────────────────────────────────────────
    years_experience: float
    """Total years of professional experience parsed from the resume."""

    education: str
    """
    Highest-level education entry as a human-readable string, e.g.
    "B.Tech, Computer Science, IIT Delhi (2018)".
    """

    # ── Decision Support ─────────────────────────────────────────────────────
    recommendation: str
    """
    Human-readable hiring recommendation bucket:
    "Strong Hire" | "Hire" | "Phone Screen" | "Pass".
    Derived from final_score thresholds.
    """

    explanation: str
    """
    Natural-language explanation of the ranking decision.  Sourced from the
    Explanation.natural_language DB column when available; otherwise generated
    inline from the ranking sub-scores.
    """

    # ── Audit ────────────────────────────────────────────────────────────────
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """UTC timestamp at which this export row was assembled."""


# ---------------------------------------------------------------------------
# Column metadata — consumed by ExcelFormatter to render headers and widths
# ---------------------------------------------------------------------------

#: Ordered list of (attribute_name, display_header, column_width_chars)
COLUMN_SCHEMA: list[tuple[str, str, int]] = [
    ("rank",             "Rank",              8),
    ("candidate_id",     "Candidate ID",      38),
    ("candidate_name",   "Candidate Name",    28),
    ("final_score",      "Final Score",       14),
    ("semantic_score",   "Semantic Score",    16),
    ("evidence_score",   "Evidence Score",    16),
    ("career_score",     "Career Score",      14),
    ("behavior_score",   "Behavior Score",    16),
    ("model_score",      "Model Score",       14),
    ("matching_skills",  "Matching Skills",   50),
    ("missing_skills",   "Missing Skills",    40),
    ("years_experience", "Years Experience",  18),
    ("education",        "Education",         40),
    ("recommendation",   "Recommendation",    18),
    ("confidence",       "Confidence",        14),
    ("explanation",      "Explanation",       80),
    ("resume_path",      "Resume Path",       60),
    ("job_id",           "Job ID",            38),
    ("timestamp",        "Timestamp",         22),
]

#: Score columns that receive percentage formatting and color-scale CF.
SCORE_COLUMNS: set[str] = {
    "final_score",
    "semantic_score",
    "evidence_score",
    "career_score",
    "behavior_score",
    "model_score",
    "confidence",
}

#: Map from final_score threshold to recommendation label.
RECOMMENDATION_THRESHOLDS: list[tuple[float, str]] = [
    (0.80, "Strong Hire"),
    (0.65, "Hire"),
    (0.50, "Phone Screen"),
    (0.00, "Pass"),
]


def score_to_recommendation(final_score: float) -> str:
    """Convert a final score to a recommendation label."""
    for threshold, label in RECOMMENDATION_THRESHOLDS:
        if final_score >= threshold:
            return label
    return "Pass"


def score_to_confidence(final_score: float) -> float:
    """
    Derive a confidence value from the final score.

    Uses a linear mapping that emphasises the decision-relevant mid-range:
    - score >= 0.80  →  confidence >= 0.90
    - score == 0.50  →  confidence == 0.60
    - score == 0.00  →  confidence == 0.10

    The formula is: confidence = 0.10 + 0.80 * final_score, clamped to
    [0.10, 0.99].  This avoids false certainty at the extremes.
    """
    raw = 0.10 + 0.80 * final_score
    return round(min(0.99, max(0.10, raw)), 4)
