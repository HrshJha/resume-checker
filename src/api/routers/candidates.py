"""
Candidates router — resume upload, processing, and retrieval.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_session
from src.api.db_models import User
from src.api.dependencies import get_current_user, get_settings
from src.api.models.request_models import (
    BulkUploadResponse,
    CandidateDetailResponse,
    CandidateStatusResponse,
    CandidateUploadResponse,
)
from src.api.repositories.candidate_repo import CandidateRepository
from src.utils.file_validator import validate_file_bytes, FileValidationError
from src.utils.logger import get_logger

logger = get_logger("candidates_router")

router = APIRouter()


async def _process_resume(candidate_id: str, file_path: str) -> None:
    """Background task: parse, embed, extract features, index."""
    # This runs in background — imports here to avoid circular
    from src.api.database import _async_session_factory
    from src.api.repositories.candidate_repo import CandidateRepository
    from src.resume.resume_parser import parse_resume
    from src.utils.skill_canonicalizer import SkillCanonicalizer

    if _async_session_factory is None:
        logger.error("Database not initialized for background task")
        return

    async with _async_session_factory() as session:
        repo = CandidateRepository(session)

        try:
            await repo.update_status(candidate_id, "processing")

            # Parse resume
            canonicalizer = SkillCanonicalizer()
            parsed = parse_resume(file_path, candidate_id=candidate_id, canonicalizer=canonicalizer)

            # Update parsed data
            await repo.update_parsed_data(
                candidate_id=candidate_id,
                parsed_data=parsed.to_dict(),
                skills=parsed.skills,
                experience_years=parsed.experience_years,
                education=parsed.education,
                projects=parsed.projects,
                certifications=parsed.certifications,
                links={
                    "github": parsed.links.github if parsed.links else None,
                    "linkedin": parsed.links.linkedin if parsed.links else None,
                    "portfolio": parsed.links.portfolio if parsed.links else None,
                },
            )

            # Mark as indexed
            await repo.update_status(candidate_id, "indexed")
            await session.commit()

            logger.info(f"Resume processed successfully: {candidate_id}")

        except Exception as e:
            logger.error(f"Resume processing failed for {candidate_id}: {e}")
            await repo.update_status(candidate_id, "failed")
            await session.commit()


@router.post("/upload", response_model=CandidateUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a single resume for processing."""
    settings = get_settings()

    # Read file contents
    contents = await file.read()

    # Validate file
    try:
        file_type = validate_file_bytes(
            contents,
            filename=file.filename or "unknown",
            max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
        )
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Generate candidate ID and save file
    candidate_id = str(uuid.uuid4())
    ext = "pdf" if file_type == "pdf" else "docx"
    file_name = f"{candidate_id}.{ext}"
    file_path = Path(settings.upload_dir) / file_name
    file_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_file() -> None:
        with open(file_path, "wb") as f:
            f.write(contents)

    await anyio.to_thread.run_sync(_write_file)

    # Create candidate record
    repo = CandidateRepository(session)
    await repo.create(
        candidate_id=candidate_id,
        raw_resume_path=str(file_path),
        processing_status="pending",
    )
    await session.commit()

    # Queue background processing
    background_tasks.add_task(_process_resume, candidate_id, str(file_path))

    return CandidateUploadResponse(
        candidate_id=candidate_id,
        status="processing",
        message="Resume queued for indexing",
    )


@router.post("/bulk-upload", response_model=BulkUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_resumes(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload multiple resumes for batch processing."""
    settings = get_settings()

    if len(files) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 500 files per batch",
        )

    batch_id = str(uuid.uuid4())
    candidate_ids: list[str] = []
    repo = CandidateRepository(session)

    for file in files:
        contents = await file.read()

        try:
            file_type = validate_file_bytes(contents, filename=file.filename or "unknown")
        except FileValidationError:
            continue  # Skip invalid files

        candidate_id = str(uuid.uuid4())
        ext = "pdf" if file_type == "pdf" else "docx"
        file_path = Path(settings.upload_dir) / f"{candidate_id}.{ext}"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(contents)

        await repo.create(
            candidate_id=candidate_id,
            raw_resume_path=str(file_path),
            processing_status="pending",
        )

        background_tasks.add_task(_process_resume, candidate_id, str(file_path))
        candidate_ids.append(candidate_id)

    return BulkUploadResponse(
        batch_id=batch_id,
        candidate_ids=candidate_ids,
        status="processing",
        count=len(candidate_ids),
    )


@router.get("/upload", include_in_schema=False)
async def upload_resume_help():
    """Human-friendly helper for browser visits to the upload endpoint."""
    return {
        "detail": "Resume upload requires POST with multipart form data.",
        "docs": "/api/docs",
        "endpoint": "POST /api/v1/candidates/upload",
        "auth": "Register/login, then use the bearer token in Swagger Authorize.",
    }


@router.get("/{candidate_id}", response_model=CandidateDetailResponse)
async def get_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get candidate details by ID."""
    repo = CandidateRepository(session)
    candidate = await repo.get_by_id(candidate_id)

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    parsed_data = candidate.parsed_data or {}  # type: ignore

    return CandidateDetailResponse(
        candidate_id=candidate.candidate_id,  # type: ignore
        skills=candidate.skills or [],  # type: ignore
        experience_years=candidate.experience_years or 0.0,  # type: ignore
        education=candidate.education or [],  # type: ignore
        projects_count=len(candidate.projects or []),
        parsed_sections=list(parsed_data.get("sections", {}).keys()),
        processing_status=candidate.processing_status or "pending",  # type: ignore
    )


@router.get("/{candidate_id}/status", response_model=CandidateStatusResponse)
async def get_candidate_status(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Check candidate processing status."""
    repo = CandidateRepository(session)
    candidate = await repo.get_by_id(candidate_id)

    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return CandidateStatusResponse(
        candidate_id=candidate.candidate_id,  # type: ignore
        status=candidate.processing_status or "pending",  # type: ignore
        indexed_at=candidate.indexed_at,  # type: ignore
    )


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a candidate and all associated data (GDPR-compliant)."""
    repo = CandidateRepository(session)
    candidate = await repo.get_by_id(candidate_id)

    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Delete file from disk
    if candidate.raw_resume_path:
        file_path = Path(candidate.raw_resume_path)
        if file_path.exists():
            file_path.unlink()

    # Delete from database (cascades to rankings, explanations, features)
    await repo.delete(candidate_id)
