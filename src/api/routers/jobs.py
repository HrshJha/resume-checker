"""
Job descriptions router — upload, parse, and retrieve JDs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import User
from src.api.dependencies import get_current_user
from src.api.models.request_models import JDIntelligenceResponse, JDUploadRequest
from src.api.repositories.jd_repo import JDRepository
from src.jd.domain_classifier import classify_domain
from src.jd.jd_parser import parse_jd
from src.jd.seniority_detector import detect_seniority
from src.jd.skill_extractor import extract_skills
from src.utils.skill_canonicalizer import SkillCanonicalizer

router = APIRouter()


@router.post("/", response_model=JDIntelligenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_jd(
    request: JDUploadRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload and parse a job description."""
    # Parse JD
    parsed = parse_jd(request.jd_text)

    # Extract skills
    canonicalizer = SkillCanonicalizer()
    sections_as_dicts = [{"name": s.name, "content": s.content} for s in parsed.sections]
    skill_result = extract_skills(sections_as_dicts, parsed.cleaned_text, canonicalizer)

    # Detect seniority
    seniority = detect_seniority(parsed.cleaned_text, parsed.title)

    # Classify domain
    domain_result = classify_domain(parsed.cleaned_text, parsed.title)

    # Store in database
    repo = JDRepository(session)
    jd = await repo.create(
        raw_text=request.jd_text,
        role=parsed.title,
        seniority=seniority,
        required_skills=[s.name for s in skill_result.required_skills],
        preferred_skills=[s.name for s in skill_result.preferred_skills],
        soft_skills=[s.name for s in skill_result.soft_skills],
        industry=domain_result.primary_domain,
        domain=domain_result.primary_domain,
        experience_min_years=parsed.experience_min_years,
        experience_max_years=parsed.experience_max_years,
        created_by=current_user.user_id,
    )

    return JDIntelligenceResponse(
        jd_id=jd.jd_id,  # type: ignore
        role=parsed.title or "Unknown",
        seniority=seniority,
        required_skills=[s.name for s in skill_result.required_skills],
        preferred_skills=[s.name for s in skill_result.preferred_skills],
        soft_skills=[s.name for s in skill_result.soft_skills],
        industry=domain_result.primary_domain,
        experience_range={
            "min_years": parsed.experience_min_years or 0,
            "max_years": parsed.experience_max_years or 0,
        },
        status="processed",
    )


@router.get("/{jd_id}", response_model=JDIntelligenceResponse)
async def get_jd(
    jd_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a parsed job description by ID."""
    repo = JDRepository(session)
    jd = await repo.get_by_id(jd_id)

    if jd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="JD not found",
        )

    return JDIntelligenceResponse(
        jd_id=jd.jd_id,  # type: ignore
        role=jd.role or "Unknown",  # type: ignore
        seniority=jd.seniority or 2,  # type: ignore
        required_skills=jd.required_skills or [],  # type: ignore
        preferred_skills=jd.preferred_skills or [],  # type: ignore
        soft_skills=jd.soft_skills or [],  # type: ignore
        industry=jd.industry or "",  # type: ignore
        experience_range={
            "min_years": jd.experience_min_years or 0,  # type: ignore
            "max_years": jd.experience_max_years or 0,  # type: ignore
        },
        status="processed",
    )


@router.get("/")
async def list_jds(
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all job descriptions."""
    repo = JDRepository(session)
    jds = await repo.list_all(skip=skip, limit=limit)
    return [
        {
            "jd_id": jd.jd_id,
            "role": jd.role,
            "industry": jd.industry,
            "created_at": jd.created_at.isoformat() if jd.created_at else None,
        }
        for jd in jds
    ]
