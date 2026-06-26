"""
OCR parser for scanned PDF resumes using pytesseract + Pillow.

Converts each PDF page to an image, then runs OCR to extract text.
Used as a fallback when pdfplumber and PyMuPDF fail to extract text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("ocr_parser")


@dataclass
class OCRParseResult:
    """Result of OCR parsing."""

    full_text: str
    pages: list[str] = field(default_factory=list)
    page_count: int = 0
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


def parse_scanned_pdf(file_path: str | Path) -> OCRParseResult:
    """
    Parse a scanned PDF using OCR (pytesseract).

    Converts PDF pages to images using PyMuPDF, then runs OCR.

    Args:
        file_path: Path to the scanned PDF.

    Returns:
        OCRParseResult with extracted text.
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        import io
    except ImportError as e:
        logger.error(f"OCR dependencies not available: {e}")
        return OCRParseResult(
            full_text="",
            warnings=[f"OCR dependencies missing: {e}"],
        )

    file_path = Path(file_path)
    pages: list[str] = []
    warnings: list[str] = []
    total_confidence = 0.0

    try:
        doc = fitz.open(str(file_path))
        page_count = len(doc)

        for page_num in range(page_count):
            page = doc[page_num]

            # Render page to image (300 DPI for good OCR quality)
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Run OCR
            try:
                # Get detailed OCR data for confidence
                ocr_data = pytesseract.image_to_data(
                    img, output_type=pytesseract.Output.DICT
                )

                page_text = pytesseract.image_to_string(img)
                pages.append(page_text)

                # Compute average confidence for this page
                confidences = [
                    int(c)
                    for c in ocr_data.get("conf", [])
                    if str(c).isdigit() and int(c) > 0
                ]
                if confidences:
                    page_conf = sum(confidences) / len(confidences)
                    total_confidence += page_conf
                    if page_conf < 50:
                        warnings.append(
                            f"Page {page_num + 1}: Low OCR confidence ({page_conf:.0f}%)"
                        )

            except Exception as e:
                warnings.append(f"Page {page_num + 1}: OCR failed: {e}")
                pages.append("")

        doc.close()

        full_text = "\n".join(pages)
        avg_confidence = total_confidence / page_count if page_count > 0 else 0.0

        logger.info(
            f"OCR completed for {file_path.name}: "
            f"{page_count} pages, avg confidence: {avg_confidence:.0f}%"
        )

        return OCRParseResult(
            full_text=full_text,
            pages=pages,
            page_count=page_count,
            confidence=avg_confidence / 100.0,
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"OCR parsing failed for {file_path}: {e}")
        return OCRParseResult(
            full_text="",
            warnings=[f"OCR failed: {e}"],
        )
