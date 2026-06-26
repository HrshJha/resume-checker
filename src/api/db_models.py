"""
SQLAlchemy ORM models for the Candidate Intelligence System.

Tables:
- users: recruiter/admin accounts
- job_descriptions: parsed JD data
- candidates: parsed resume data
- rankings: JD-candidate ranking results
- explanations: SHAP explanations per ranking
- feature_store_index: feature version tracking
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from src.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _gen_uuid() -> str:
    return str(uuid.uuid4())


# Use JSON type that works across SQLite and PostgreSQL
_JSONType = JSON


class User(Base):
    """Recruiter / admin user account."""

    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=_gen_uuid)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="recruiter")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    job_descriptions = relationship("JobDescription", back_populates="created_by_user")

    __table_args__ = (
        CheckConstraint("role IN ('recruiter', 'admin')", name="ck_user_role"),
    )


class JobDescription(Base):
    """Parsed job description with structured intelligence."""

    __tablename__ = "job_descriptions"

    jd_id = Column(String(36), primary_key=True, default=_gen_uuid)
    raw_text = Column(Text, nullable=False)
    role = Column(String(200))
    seniority = Column(Integer)
    required_skills = Column(_JSONType)
    preferred_skills = Column(_JSONType)
    soft_skills = Column(_JSONType)
    industry = Column(String(100))
    domain = Column(String(100))
    experience_min_years = Column(Float)
    experience_max_years = Column(Float)
    embedding_path = Column(String(500))
    created_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    created_by_user = relationship("User", back_populates="job_descriptions")
    rankings = relationship("Ranking", back_populates="job_description", cascade="all, delete-orphan")


class Candidate(Base):
    """Parsed resume with structured data and processing status."""

    __tablename__ = "candidates"

    candidate_id = Column(String(36), primary_key=True, default=_gen_uuid)
    raw_resume_path = Column(String(500))
    parsed_data = Column(_JSONType)
    skills = Column(_JSONType)
    experience_years = Column(Float)
    education = Column(_JSONType)
    projects = Column(_JSONType)
    certifications = Column(_JSONType)
    links = Column(_JSONType)
    embedding_path = Column(String(500))
    feature_store_path = Column(String(500))
    processing_status = Column(String(20), default="pending", index=True)
    indexed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    rankings = relationship("Ranking", back_populates="candidate", cascade="all, delete-orphan")
    feature_entries = relationship("FeatureStoreIndex", back_populates="candidate", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'indexed', 'failed')",
            name="ck_candidate_status",
        ),
    )


class Ranking(Base):
    """JD-candidate ranking result with multi-dimensional scores."""

    __tablename__ = "rankings"

    ranking_id = Column(String(36), primary_key=True, default=_gen_uuid)
    jd_id = Column(
        String(36),
        ForeignKey("job_descriptions.jd_id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    rank = Column(Integer, nullable=False)
    semantic_score = Column(Float)
    evidence_score = Column(Float)
    career_score = Column(Float)
    behavior_score = Column(Float)
    final_score = Column(Float, nullable=False)
    feature_version = Column(String(20))
    model_version = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    job_description = relationship("JobDescription", back_populates="rankings")
    candidate = relationship("Candidate", back_populates="rankings")
    explanation = relationship("Explanation", back_populates="ranking", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("jd_id", "candidate_id", name="uq_ranking_jd_candidate"),
        Index("idx_rankings_jd_id", "jd_id"),
        Index("idx_rankings_candidate_id", "candidate_id"),
        Index("idx_rankings_final_score", "jd_id", "final_score"),
    )


class Explanation(Base):
    """SHAP-based explanation for a ranking decision."""

    __tablename__ = "explanations"

    explanation_id = Column(String(36), primary_key=True, default=_gen_uuid)
    ranking_id = Column(
        String(36),
        ForeignKey("rankings.ranking_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    shap_values = Column(_JSONType, nullable=False)
    feature_contributions = Column(_JSONType, nullable=False)
    natural_language = Column(Text)
    counterfactuals = Column(_JSONType)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    ranking = relationship("Ranking", back_populates="explanation")


class FeatureStoreIndex(Base):
    """Tracks feature store versions per candidate."""

    __tablename__ = "feature_store_index"

    feature_id = Column(String(36), primary_key=True, default=_gen_uuid)
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_version = Column(String(20), nullable=False)
    parquet_path = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="feature_entries")

    __table_args__ = (
        UniqueConstraint("candidate_id", "feature_version", name="uq_feature_candidate_version"),
        Index("idx_feature_store_candidate", "candidate_id"),
    )
