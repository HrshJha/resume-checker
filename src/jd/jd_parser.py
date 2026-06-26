"""
Job Description parser — cleans, sections, and structures raw JD text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger
from src.utils.text_cleaner import clean_text

logger = get_logger("jd_parser")

# JD section patterns
_JD_SECTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "about": [
        re.compile(r"^(about\s+(the\s+)?(company|role|us|team))\b", re.IGNORECASE),
        re.compile(r"^(company\s+)?(overview|description)\b", re.IGNORECASE),
    ],
    "responsibilities": [
        re.compile(r"^(key\s+)?(responsibilities|duties)\b", re.IGNORECASE),
        re.compile(r"^what\s+you.*(do|own|build)\b", re.IGNORECASE),
        re.compile(r"^(the\s+)?role\b", re.IGNORECASE),
        re.compile(r"^you\s+will\b", re.IGNORECASE),
    ],
    "requirements": [
        re.compile(r"^(minimum\s+)?requirements?\b", re.IGNORECASE),
        re.compile(r"^(required\s+)?(qualifications?|skills?)\b", re.IGNORECASE),
        re.compile(r"^what\s+you.*(need|bring|have)\b", re.IGNORECASE),
        re.compile(r"^must\s+have\b", re.IGNORECASE),
        re.compile(r"^who\s+you\s+are\b", re.IGNORECASE),
    ],
    "preferred": [
        re.compile(r"^(preferred|desired|nice\s+to\s+have)\b", re.IGNORECASE),
        re.compile(r"^bonus\s*(points?|qualifications?)?\b", re.IGNORECASE),
        re.compile(r"^(additional|optional)\s+(qualifications?|skills?)\b", re.IGNORECASE),
        re.compile(r"^it.*(nice|great|plus)\b", re.IGNORECASE),
    ],
    "benefits": [
        re.compile(r"^(benefits?|perks?|what\s+we\s+offer)\b", re.IGNORECASE),
        re.compile(r"^compensation\b", re.IGNORECASE),
    ],
    "experience": [
        re.compile(r"^experience\b", re.IGNORECASE),
    ],
}

# Experience range patterns
_EXP_RANGE_RE = re.compile(
    r"(\d+)\s*[-–+to]*\s*(\d+)?\s*\+?\s*years?\s*(of\s+)?(experience|exp)?",
    re.IGNORECASE,
)


@dataclass
class JDSection:
    """A section in a job description."""
    name: str
    content: str


@dataclass
class JDParseResult:
    """Parsed job description."""
    raw_text: str
    cleaned_text: str
    title: str = ""
    sections: list[JDSection] = field(default_factory=list)
    experience_min_years: Optional[float] = None
    experience_max_years: Optional[float] = None
    warnings: list[str] = field(default_factory=list)


def _extract_experience_range(text: str) -> tuple[Optional[float], Optional[float]]:
    """Extract experience year range from text."""
    matches = _EXP_RANGE_RE.findall(text)
    if not matches:
        return None, None

    min_years = None
    max_years = None

    for match in matches:
        low = float(match[0]) if match[0] else None
        high = float(match[1]) if match[1] else None

        if low is not None:
            if min_years is None or low < min_years:
                min_years = low
        if high is not None:
            if max_years is None or high > max_years:
                max_years = high

    if min_years is not None and max_years is None:
        max_years = min_years + 3  # Default range

    return min_years, max_years


def _detect_jd_section(line: str) -> Optional[str]:
    """Check if a line is a JD section header."""
    cleaned = line.strip().rstrip(":").strip()
    if len(cleaned) > 80 or not cleaned:
        return None

    for section_name, patterns in _JD_SECTION_PATTERNS.items():
        for pattern in patterns:
            if pattern.match(cleaned):
                return section_name
    return None


def parse_jd(raw_text: str) -> JDParseResult:
    """
    Parse and structure a raw job description text.

    Args:
        raw_text: Raw JD text.

    Returns:
        JDParseResult with sections and extracted metadata.
    """
    # Clean the text
    cleaned = clean_text(
        raw_text,
        strip_html_tags=True,
        remove_jd_boilerplate=True,
    )

    warnings: list[str] = []
    lines = cleaned.split("\n")

    # Try to extract title (first non-empty, short line)
    title = ""
    for line in lines[:5]:
        stripped = line.strip()
        if stripped and len(stripped) < 100:
            title = stripped
            break

    # Detect sections
    boundaries: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        section_name = _detect_jd_section(line)
        if section_name:
            boundaries.append((i, section_name, line.strip()))

    sections: list[JDSection] = []
    if boundaries:
        for idx, (line_num, section_name, _header) in enumerate(boundaries):
            if idx + 1 < len(boundaries):
                end_line = boundaries[idx + 1][0]
            else:
                end_line = len(lines)

            content = "\n".join(lines[line_num + 1 : end_line]).strip()
            sections.append(JDSection(name=section_name, content=content))
    else:
        # No sections detected — treat as single block
        sections.append(JDSection(name="full", content=cleaned))
        warnings.append("No JD sections detected — treating as single block")

    # Extract experience range
    exp_min, exp_max = _extract_experience_range(cleaned)

    logger.debug(
        f"Parsed JD: title='{title}', {len(sections)} sections, "
        f"exp={exp_min}-{exp_max} years"
    )

    return JDParseResult(
        raw_text=raw_text,
        cleaned_text=cleaned,
        title=title,
        sections=sections,
        experience_min_years=exp_min,
        experience_max_years=exp_max,
        warnings=warnings,
    )
