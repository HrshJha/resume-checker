"""
Resume section detection using regex patterns and heuristics.

Identifies and labels resume sections (Summary, Education, Experience,
Projects, Skills, Certifications, Publications, Achievements, Links).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("section_detector")

# ---------------------------------------------------------------------------
# Section header patterns (case-insensitive)
# ---------------------------------------------------------------------------
SECTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "summary": [
        re.compile(r"^(professional\s+)?summary\b", re.IGNORECASE),
        re.compile(r"^(career\s+)?objective\b", re.IGNORECASE),
        re.compile(r"^profile\b", re.IGNORECASE),
        re.compile(r"^about\s*(me)?\b", re.IGNORECASE),
        re.compile(r"^personal\s+statement\b", re.IGNORECASE),
        re.compile(r"^executive\s+summary\b", re.IGNORECASE),
    ],
    "education": [
        re.compile(r"^education\b", re.IGNORECASE),
        re.compile(r"^academic\s+(background|qualifications?)\b", re.IGNORECASE),
        re.compile(r"^educational\s+(background|qualifications?)\b", re.IGNORECASE),
        re.compile(r"^degrees?\b", re.IGNORECASE),
    ],
    "experience": [
        re.compile(r"^(work\s+)?(experience|history)\b", re.IGNORECASE),
        re.compile(r"^professional\s+experience\b", re.IGNORECASE),
        re.compile(r"^employment\s*(history)?\b", re.IGNORECASE),
        re.compile(r"^career\s+history\b", re.IGNORECASE),
        re.compile(r"^relevant\s+experience\b", re.IGNORECASE),
    ],
    "projects": [
        re.compile(r"^projects?\b", re.IGNORECASE),
        re.compile(r"^personal\s+projects?\b", re.IGNORECASE),
        re.compile(r"^key\s+projects?\b", re.IGNORECASE),
        re.compile(r"^academic\s+projects?\b", re.IGNORECASE),
        re.compile(r"^notable\s+projects?\b", re.IGNORECASE),
    ],
    "skills": [
        re.compile(r"^(technical\s+)?skills?\b", re.IGNORECASE),
        re.compile(r"^core\s+(competenc|skills?)\b", re.IGNORECASE),
        re.compile(r"^areas?\s+of\s+expertise\b", re.IGNORECASE),
        re.compile(r"^technologies?\b", re.IGNORECASE),
        re.compile(r"^technical\s+(proficienc|competenc)\b", re.IGNORECASE),
        re.compile(r"^tools?\s*(and|&)\s*technologies?\b", re.IGNORECASE),
    ],
    "certifications": [
        re.compile(r"^certifications?\b", re.IGNORECASE),
        re.compile(r"^licenses?\s*(and|&)?\s*certifications?\b", re.IGNORECASE),
        re.compile(r"^professional\s+certifications?\b", re.IGNORECASE),
        re.compile(r"^accreditations?\b", re.IGNORECASE),
    ],
    "publications": [
        re.compile(r"^publications?\b", re.IGNORECASE),
        re.compile(r"^research\s*(papers?)?\b", re.IGNORECASE),
        re.compile(r"^papers?\b", re.IGNORECASE),
        re.compile(r"^published\s+works?\b", re.IGNORECASE),
    ],
    "achievements": [
        re.compile(r"^(achievements?|accomplishments?)\b", re.IGNORECASE),
        re.compile(r"^awards?\s*(and|&)?\s*(honors?|recognition)?\b", re.IGNORECASE),
        re.compile(r"^honors?\s*(and|&)?\s*awards?\b", re.IGNORECASE),
    ],
    "links": [
        re.compile(r"^(links?|portfolio|online\s+presence)\b", re.IGNORECASE),
        re.compile(r"^web\s*(sites?|pages?|links?)\b", re.IGNORECASE),
        re.compile(r"^social\s*(media|profiles?|links?)\b", re.IGNORECASE),
    ],
    "references": [
        re.compile(r"^references?\b", re.IGNORECASE),
    ],
    "languages": [
        re.compile(r"^languages?\b", re.IGNORECASE),
    ],
    "interests": [
        re.compile(r"^(interests?|hobbies?)\b", re.IGNORECASE),
        re.compile(r"^extra\s*curricular\b", re.IGNORECASE),
    ],
    "volunteer": [
        re.compile(r"^volunteer\b", re.IGNORECASE),
        re.compile(r"^community\s+(service|involvement)\b", re.IGNORECASE),
    ],
}


@dataclass
class Section:
    """A detected resume section."""

    name: str  # Canonical section name
    header_text: str  # Original header text
    content: str  # Section content text
    start_line: int = 0
    end_line: int = 0
    confidence: float = 1.0


@dataclass
class SectionDetectionResult:
    """Result of section detection."""

    sections: list[Section] = field(default_factory=list)
    unmatched_content: str = ""
    warnings: list[str] = field(default_factory=list)


def _is_section_header(line: str) -> Optional[str]:
    """
    Check if a line matches any section header pattern.

    Returns:
        Canonical section name if matched, None otherwise.
    """
    cleaned = line.strip().rstrip(":").strip()

    # Skip very long lines (headers are typically short)
    if len(cleaned) > 60:
        return None

    # Skip lines that are mostly numbers or symbols
    alpha_ratio = sum(1 for c in cleaned if c.isalpha()) / max(len(cleaned), 1)
    if alpha_ratio < 0.5:
        return None

    for section_name, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if pattern.match(cleaned):
                return section_name

    return None


def _is_likely_header(line: str, is_bold: bool = False, is_heading: bool = False) -> bool:
    """
    Check if a line is likely a section header based on formatting cues.

    Heuristics:
    - All caps
    - Ends with colon
    - Styled as heading/bold
    - Short length
    """
    cleaned = line.strip()
    if not cleaned:
        return False

    # Strong signals
    if is_heading or is_bold:
        return True

    # All uppercase (common in resumes)
    if cleaned.isupper() and len(cleaned) < 40:
        return True

    # Ends with colon
    if cleaned.endswith(":") and len(cleaned) < 40:
        return True

    return False


def detect_sections(
    text: str,
    paragraphs: Optional[list[dict]] = None,
) -> SectionDetectionResult:
    """
    Detect and extract sections from resume text.

    Args:
        text: Full resume text.
        paragraphs: Optional structured paragraphs from DOCX parser
                    (with is_heading, is_bold metadata).

    Returns:
        SectionDetectionResult with detected sections.
    """
    lines = text.split("\n")
    warnings: list[str] = []

    # Find section boundaries
    boundaries: list[tuple[int, str, str]] = []  # (line_idx, section_name, header_text)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Check against section patterns
        section_name = _is_section_header(stripped)
        if section_name:
            boundaries.append((i, section_name, stripped))
            continue

        # Check formatting cues from DOCX paragraphs
        if paragraphs:
            for para in paragraphs:
                if para["text"] == stripped:
                    if _is_likely_header(stripped, para.get("is_bold", False), para.get("is_heading", False)):
                        section_name = _is_section_header(stripped)
                        if section_name:
                            boundaries.append((i, section_name, stripped))
                    break

    # Extract section content
    sections: list[Section] = []
    unmatched_lines: list[str] = []

    if not boundaries:
        warnings.append("No section headers detected — treating entire text as unstructured")
        return SectionDetectionResult(
            sections=[],
            unmatched_content=text,
            warnings=warnings,
        )

    # Content before first section
    first_boundary_line = boundaries[0][0]
    pre_content = "\n".join(lines[:first_boundary_line]).strip()
    if pre_content:
        # Treat as summary/header content
        sections.append(
            Section(
                name="header",
                header_text="",
                content=pre_content,
                start_line=0,
                end_line=first_boundary_line - 1,
                confidence=0.7,
            )
        )

    # Extract content between boundaries
    for idx, (line_num, section_name, header_text) in enumerate(boundaries):
        # End line is start of next section or end of document
        if idx + 1 < len(boundaries):
            end_line = boundaries[idx + 1][0]
        else:
            end_line = len(lines)

        # Content = lines between header and next section, excluding header
        content_lines = lines[line_num + 1 : end_line]
        content = "\n".join(content_lines).strip()

        sections.append(
            Section(
                name=section_name,
                header_text=header_text,
                content=content,
                start_line=line_num,
                end_line=end_line - 1,
                confidence=1.0,
            )
        )

    logger.debug(
        f"Detected {len(sections)} sections: {[s.name for s in sections]}"
    )

    return SectionDetectionResult(
        sections=sections,
        unmatched_content="\n".join(unmatched_lines),
        warnings=warnings,
    )


def get_section_content(
    detection_result: SectionDetectionResult,
    section_name: str,
) -> Optional[str]:
    """Get content for a specific section name."""
    for section in detection_result.sections:
        if section.name == section_name:
            return section.content
    return None


def get_section_names(detection_result: SectionDetectionResult) -> list[str]:
    """Get list of detected section names."""
    return [s.name for s in detection_result.sections]
