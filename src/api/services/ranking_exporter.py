"""
Ranking exporter — thin orchestrator that glues ExportService and
ExcelFormatter together.

Follows the ``InferenceOrchestrator`` pattern: it owns the async entry points
that the router calls, delegates all DB work to ExportService, and all
formatting to ExcelFormatter.

This class is the single object the router imports from the export pipeline.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.excel_formatter import ExcelFormatter
from src.api.services.export_service import ExportService
from src.api.models.export_models import RankingExportRow
from src.api.repositories.jd_repo import JDRepository
from src.utils.logger import get_logger

logger = get_logger("ranking_exporter")


class RankingExporter:
    """
    Entry point for the XLSX export pipeline.

    Usage (from a FastAPI route)::

        exporter = RankingExporter()
        data = await exporter.export_to_bytes(jd_id=jd_id, session=session)
        return StreamingResponse(io.BytesIO(data), media_type="...")

    Usage (CLI / background task)::

        exporter = RankingExporter()
        path = await exporter.export_to_file(
            jd_id=jd_id, session=session, out_dir=Path("output")
        )
    """

    def __init__(self) -> None:
        self._formatter = ExcelFormatter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def export_to_bytes(
        self,
        jd_id: str,
        session: AsyncSession,
        top_k: int = 100,
    ) -> bytes:
        """
        Build ranking rows and return a formatted XLSX as raw bytes.

        Args:
            jd_id:   UUID of the job description.
            session: SQLAlchemy async session.
            top_k:   Maximum candidates to include (default: 100).

        Returns:
            Raw bytes of the XLSX file.

        Raises:
            ValueError: If the JD does not exist or has no rankings.
        """
        rows, job_role = await self._build_rows(jd_id, session, top_k)
        raw = self._formatter.format_to_bytes(rows, job_role=job_role)

        logger.info(
            f"XLSX export produced: {len(raw):,} bytes, "
            f"{len(rows)} rows, JD={jd_id}"
        )
        return raw

    async def export_to_file(
        self,
        jd_id: str,
        session: AsyncSession,
        out_dir: Path | str = Path("output"),
        top_k: int = 100,
    ) -> Path:
        """
        Build ranking rows, write an XLSX file to disk, and return its path.

        The filename is deterministic: ``ranking_{jd_id}.xlsx``.  An existing
        file at that path is overwritten so repeated exports stay idempotent.

        Args:
            jd_id:   UUID of the job description.
            session: SQLAlchemy async session.
            out_dir: Directory to write the file into.
            top_k:   Maximum candidates to include.

        Returns:
            ``Path`` to the written file.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        rows, job_role = await self._build_rows(jd_id, session, top_k)
        wb = self._formatter.format_workbook(rows, job_role=job_role)

        out_path = out_dir / f"ranking_{jd_id}.xlsx"
        wb.save(str(out_path))

        logger.info(
            f"XLSX export written to disk: {out_path} "
            f"({out_path.stat().st_size:,} bytes)"
        )
        return out_path

    async def get_rows_only(
        self,
        jd_id: str,
        session: AsyncSession,
        top_k: int = 100,
    ) -> list[RankingExportRow]:
        """
        Return the assembled export rows WITHOUT producing an XLSX.

        Useful for testing and for callers that need the data in Python form.
        """
        rows, _ = await self._build_rows(jd_id, session, top_k)
        return rows

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _build_rows(
        self,
        jd_id: str,
        session: AsyncSession,
        top_k: int,
    ) -> tuple[list[RankingExportRow], str]:
        """
        Orchestrate data assembly and return (rows, job_role_string).

        Fetches the JD role separately so the formatter can use it for
        the sheet tab name and the summary sheet.
        """
        service = ExportService(session)
        rows = await service.build_ranking_rows(jd_id=jd_id, top_k=top_k)

        # Retrieve job role for the sheet title
        jd_repo = JDRepository(session)
        jd = await jd_repo.get_by_id(jd_id)
        job_role: str = (
            str(jd.role).strip() if jd and jd.role else "Candidate Ranking"
        )

        return rows, job_role
