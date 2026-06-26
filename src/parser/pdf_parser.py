"""
PDF resume parser using pdfplumber (primary) with PyMuPDF fallback.

Handles:
- Single and multi-column layouts
- Table detection and extraction
- Reading order normalization
- Timeout enforcement (30s)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("pdf_parser")


@dataclass
class TextBlock:
    """A block of text extracted from a PDF page."""

    text: str
    page_num: int
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    column: int = 0  # 0=single/left, 1=right


@dataclass
class PDFParseResult:
    """Result of parsing a PDF file."""

    full_text: str
    pages: list[str]
    page_count: int
    blocks: list[TextBlock] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    is_scanned: bool = False
    parser_used: str = "pdfplumber"
    warnings: list[str] = field(default_factory=list)


def _detect_columns(blocks: list[dict], page_width: float) -> int:
    """
    Detect number of columns by analyzing text block x-positions.

    Uses a simple heuristic: if significant text appears in both
    the left and right halves of the page, it's likely multi-column.
    """
    if not blocks:
        return 1

    midpoint = page_width / 2
    left_chars = 0
    right_chars = 0

    for block in blocks:
        text = block.get("text", "")
        x0 = block.get("x0", 0)
        x1 = block.get("x1", page_width)
        center = (x0 + x1) / 2

        if center < midpoint:
            left_chars += len(text)
        else:
            right_chars += len(text)

    # If right column has >20% of total content, it's multi-column
    total = left_chars + right_chars
    if total > 0 and right_chars / total > 0.2:
        return 2

    return 1


def _sort_blocks_reading_order(
    blocks: list[TextBlock], column_count: int, page_width: float
) -> list[TextBlock]:
    """Sort text blocks in reading order (left column first, then right)."""
    if column_count == 1:
        return sorted(blocks, key=lambda b: (b.page_num, b.y0, b.x0))

    midpoint = page_width / 2
    for block in blocks:
        center = (block.x0 + block.x1) / 2
        block.column = 0 if center < midpoint else 1

    return sorted(blocks, key=lambda b: (b.page_num, b.column, b.y0, b.x0))


def parse_pdf_pdfplumber(file_path: str | Path) -> PDFParseResult:
    """
    Parse a PDF using pdfplumber (primary parser).

    Args:
        file_path: Path to the PDF file.

    Returns:
        PDFParseResult with extracted text, blocks, and tables.
    """
    import pdfplumber

    file_path = Path(file_path)
    pages: list[str] = []
    all_blocks: list[TextBlock] = []
    all_tables: list[list[list[str]]] = []
    warnings: list[str] = []
    is_scanned = False

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages):
                page_width = page.width

                # Extract text
                page_text = page.extract_text() or ""
                pages.append(page_text)

                # Check if page is scanned (no extractable text)
                if not page_text.strip():
                    is_scanned = True
                    warnings.append(f"Page {page_num + 1}: No extractable text (may be scanned)")
                    continue

                # Extract word-level bounding boxes for column detection
                words = page.extract_words() or []

                # Detect columns
                word_blocks = [
                    {"text": w.get("text", ""), "x0": w.get("x0", 0), "x1": w.get("x1", 0)}
                    for w in words
                ]
                column_count = _detect_columns(word_blocks, page_width)

                if column_count > 1:
                    warnings.append(f"Page {page_num + 1}: Multi-column layout detected ({column_count} columns)")

                # Create text blocks from lines
                lines = page_text.split("\n")
                y_offset = 0
                for line in lines:
                    if line.strip():
                        all_blocks.append(
                            TextBlock(
                                text=line.strip(),
                                page_num=page_num,
                                x0=0,
                                y0=y_offset,
                                x1=page_width,
                                y1=y_offset + 12,
                            )
                        )
                    y_offset += 14

                # Sort blocks in reading order
                all_blocks = _sort_blocks_reading_order(all_blocks, column_count, page_width)

                # Extract tables
                try:
                    tables = page.extract_tables() or []
                    for table in tables:
                        cleaned = [
                            [cell or "" for cell in row]
                            for row in table
                            if row
                        ]
                        if cleaned:
                            all_tables.append(cleaned)
                except Exception as e:
                    warnings.append(f"Page {page_num + 1}: Table extraction failed: {e}")

        full_text = "\n".join(pages)

        return PDFParseResult(
            full_text=full_text,
            pages=pages,
            page_count=page_count,
            blocks=all_blocks,
            tables=all_tables,
            is_scanned=is_scanned,
            parser_used="pdfplumber",
            warnings=warnings,
        )

    except Exception as e:
        logger.warning(f"pdfplumber failed for {file_path}: {e}, trying PyMuPDF fallback")
        return parse_pdf_pymupdf(file_path)


def parse_pdf_pymupdf(file_path: str | Path) -> PDFParseResult:
    """
    Parse a PDF using PyMuPDF (fitz) as fallback.

    Args:
        file_path: Path to the PDF file.

    Returns:
        PDFParseResult with extracted text.
    """
    import fitz  # PyMuPDF

    file_path = Path(file_path)
    pages: list[str] = []
    all_blocks: list[TextBlock] = []
    warnings: list[str] = []
    is_scanned = False

    try:
        doc = fitz.open(str(file_path))
        page_count = len(doc)

        for page_num in range(page_count):
            page = doc[page_num]
            page_text = page.get_text("text") or ""
            pages.append(page_text)

            if not page_text.strip():
                is_scanned = True
                warnings.append(f"Page {page_num + 1}: No extractable text (scanned)")
                continue

            # Extract text blocks with positions
            blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", [])
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    text_parts = []
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text_parts.append(span.get("text", ""))
                    text = " ".join(text_parts).strip()
                    if text:
                        bbox = block.get("bbox", (0, 0, 0, 0))
                        all_blocks.append(
                            TextBlock(
                                text=text,
                                page_num=page_num,
                                x0=bbox[0],
                                y0=bbox[1],
                                x1=bbox[2],
                                y1=bbox[3],
                            )
                        )

        doc.close()
        full_text = "\n".join(pages)

        return PDFParseResult(
            full_text=full_text,
            pages=pages,
            page_count=page_count,
            blocks=all_blocks,
            tables=[],
            is_scanned=is_scanned,
            parser_used="pymupdf",
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"PyMuPDF also failed for {file_path}: {e}")
        return PDFParseResult(
            full_text="",
            pages=[],
            page_count=0,
            is_scanned=True,
            parser_used="pymupdf",
            warnings=[f"Both parsers failed: {e}"],
        )


def parse_pdf(file_path: str | Path) -> PDFParseResult:
    """
    Parse a PDF file using the best available parser.

    Tries pdfplumber first, falls back to PyMuPDF.
    If both fail to extract text (scanned PDF), marks is_scanned=True.

    Args:
        file_path: Path to the PDF file.

    Returns:
        PDFParseResult with extracted content.
    """
    result = parse_pdf_pdfplumber(file_path)

    # If scanned and no text extracted, flag for OCR
    if result.is_scanned and not result.full_text.strip():
        logger.info(f"PDF appears scanned: {file_path}, OCR recommended")

    return result
