"""
Pydantic v2 request and response models for all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Request Models
# ============================================================

class JDUploadRequest(BaseModel):
    """Request body for uploading a job description."""
    jd_text: str = Field(..., min_length=50, max_length=50000, description="Raw JD text")


class RankRequest(BaseModel):
    """Request body for ranking candidates against a JD."""
    jd_id: str = Field(..., description="Job description ID")
    top_k: int = Field(default=20, ge=1, le=100, description="Number of results")
    filters: Optional["FilterModel"] = None


class FilterModel(BaseModel):
    """Optional filters for ranking."""
    experience_min: Optional[float] = None
    availability_days: Optional[int] = None
    work_auth: Optional[str] = None


class TokenRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class UserCreateRequest(BaseModel):
    """Create user request."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="recruiter", pattern="^(recruiter|admin)$")


# ============================================================
# Response Models
# ============================================================

class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class JDIntelligenceResponse(BaseModel):
    """Parsed JD response."""
    jd_id: str
    role: str
    seniority: int
    required_skills: list[str]
    preferred_skills: list[str]
    soft_skills: list[str]
    industry: str
    experience_range: Optional[dict[str, float]] = None
    status: str = "processed"


class CandidateUploadResponse(BaseModel):
    """Single resume upload response."""
    candidate_id: str
    status: str = "processing"
    message: str = "Resume queued for indexing"


class BulkUploadResponse(BaseModel):
    """Bulk resume upload response."""
    batch_id: str
    candidate_ids: list[str]
    status: str = "processing"
    count: int


class CandidateDetailResponse(BaseModel):
    """Candidate detail response."""
    candidate_id: str
    skills: list[str]
    experience_years: float
    education: list[dict[str, Any]]
    projects_count: int
    evidence_score: Optional[float] = None
    career_score: Optional[float] = None
    parsed_sections: list[str]
    processing_status: str


class CandidateStatusResponse(BaseModel):
    """Candidate processing status."""
    candidate_id: str
    status: str
    indexed_at: Optional[datetime] = None


class RankResultItem(BaseModel):
    """A single candidate in the ranked results."""
    rank: int
    candidate_id: str
    final_score: float
    semantic_score: float
    evidence_score: float
    career_score: float
    behavior_score: float
    explanation_summary: str


class RankedListResponse(BaseModel):
    """Complete ranking response."""
    jd_id: str
    total_candidates_screened: int
    results: list[RankResultItem]
    processing_time_seconds: float


class ExplanationResponse(BaseModel):
    """Detailed explanation for a ranking decision."""
    candidate_id: str
    rank: int
    final_score: float
    shap_values: dict[str, float]
    feature_contributions: list[dict[str, Any]]
    natural_language_explanation: str
    counterfactuals: list[dict[str, Any]]


class FairnessReportResponse(BaseModel):
    """Fairness audit report."""
    jd_id: str
    demographic_parity: Optional[float] = None
    feature_importances: dict[str, float]
    calibration_brier_score: Optional[float] = None
    feature_audit: dict[str, Any]
    generated_at: datetime


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    model_versions: dict[str, str]
    faiss_index_size: int
    uptime_seconds: float
    db_connection: str = "ok"


class ErrorResponse(BaseModel):
    """Error response schema."""
    detail: str
    error_code: str
    timestamp: datetime
