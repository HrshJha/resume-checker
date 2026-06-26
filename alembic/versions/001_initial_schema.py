"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="recruiter"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('recruiter', 'admin')", name="ck_user_role"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # --- job_descriptions ---
    op.create_table(
        "job_descriptions",
        sa.Column("jd_id", sa.String(36), primary_key=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("role", sa.String(200)),
        sa.Column("seniority", sa.Integer()),
        sa.Column("required_skills", sa.JSON()),
        sa.Column("preferred_skills", sa.JSON()),
        sa.Column("soft_skills", sa.JSON()),
        sa.Column("industry", sa.String(100)),
        sa.Column("domain", sa.String(100)),
        sa.Column("experience_min_years", sa.Float()),
        sa.Column("experience_max_years", sa.Float()),
        sa.Column("embedding_path", sa.String(500)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- candidates ---
    op.create_table(
        "candidates",
        sa.Column("candidate_id", sa.String(36), primary_key=True),
        sa.Column("raw_resume_path", sa.String(500)),
        sa.Column("parsed_data", sa.JSON()),
        sa.Column("skills", sa.JSON()),
        sa.Column("experience_years", sa.Float()),
        sa.Column("education", sa.JSON()),
        sa.Column("projects", sa.JSON()),
        sa.Column("certifications", sa.JSON()),
        sa.Column("links", sa.JSON()),
        sa.Column("embedding_path", sa.String(500)),
        sa.Column("feature_store_path", sa.String(500)),
        sa.Column("processing_status", sa.String(20), server_default="pending"),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'indexed', 'failed')",
            name="ck_candidate_status",
        ),
    )
    op.create_index("idx_candidates_status", "candidates", ["processing_status"])

    # --- rankings ---
    op.create_table(
        "rankings",
        sa.Column("ranking_id", sa.String(36), primary_key=True),
        sa.Column("jd_id", sa.String(36), sa.ForeignKey("job_descriptions.jd_id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("semantic_score", sa.Float()),
        sa.Column("evidence_score", sa.Float()),
        sa.Column("career_score", sa.Float()),
        sa.Column("behavior_score", sa.Float()),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("feature_version", sa.String(20)),
        sa.Column("model_version", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("jd_id", "candidate_id", name="uq_ranking_jd_candidate"),
    )
    op.create_index("idx_rankings_jd_id", "rankings", ["jd_id"])
    op.create_index("idx_rankings_candidate_id", "rankings", ["candidate_id"])
    op.create_index("idx_rankings_final_score", "rankings", ["jd_id", "final_score"])

    # --- explanations ---
    op.create_table(
        "explanations",
        sa.Column("explanation_id", sa.String(36), primary_key=True),
        sa.Column("ranking_id", sa.String(36), sa.ForeignKey("rankings.ranking_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("shap_values", sa.JSON(), nullable=False),
        sa.Column("feature_contributions", sa.JSON(), nullable=False),
        sa.Column("natural_language", sa.Text()),
        sa.Column("counterfactuals", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- feature_store_index ---
    op.create_table(
        "feature_store_index",
        sa.Column("feature_id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_version", sa.String(20), nullable=False),
        sa.Column("parquet_path", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "feature_version", name="uq_feature_candidate_version"),
    )
    op.create_index("idx_feature_store_candidate", "feature_store_index", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("feature_store_index")
    op.drop_table("explanations")
    op.drop_table("rankings")
    op.drop_table("candidates")
    op.drop_table("job_descriptions")
    op.drop_table("users")
