"""
Education section parser — extracts academic qualifications.

Extracts: institution, degree, major, graduation year, GPA/CGPA,
relevant coursework.
"""

from __future__ import annotations

import re

from src.utils.logger import get_logger

logger = get_logger("education_parser")

# Degree patterns
_DEGREE_PATTERNS = {
    "phd": re.compile(r"\b(Ph\.?D\.?|Doctor\w*|Doctorate)\b", re.IGNORECASE),
    "master": re.compile(
        r"\b(M\.?S\.?|M\.?Sc\.?|M\.?A\.?|M\.?Tech\.?|M\.?Eng\.?|"
        r"Master'?s?|MBA|M\.?B\.?A\.?|MCA|M\.?C\.?A\.?)\b",
        re.IGNORECASE,
    ),
    "bachelor": re.compile(
        r"\b(B\.?S\.?|B\.?Sc\.?|B\.?A\.?|B\.?Tech\.?|B\.?Eng\.?|"
        r"Bachelor'?s?|BBA|B\.?B\.?A\.?|BCA|B\.?C\.?A\.?|B\.?E\.?)\b",
        re.IGNORECASE,
    ),
    "diploma": re.compile(r"\b(Diploma|Associate'?s?|A\.?S\.?|A\.?A\.?)\b", re.IGNORECASE),
    "high_school": re.compile(r"\b(High\s+School|Secondary|HSC|CBSE|ICSE|12th|XIIth)\b", re.IGNORECASE),
}

# GPA/CGPA patterns
_GPA_PATTERN = re.compile(
    r"(?:GPA|CGPA|CPI|Grade|Score)[\s:]*(\d+\.?\d*)\s*/?\s*(\d+\.?\d*)?",
    re.IGNORECASE,
)
_PERCENTAGE_PATTERN = re.compile(r"(\d{2,3}\.?\d*)\s*%")

# Year pattern
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Major/field of study patterns
_MAJOR_KEYWORDS = [
    "computer science", "computer engineering", "software engineering",
    "information technology", "data science", "artificial intelligence",
    "electrical engineering", "electronics", "mechanical engineering",
    "mathematics", "statistics", "physics", "chemistry",
    "business administration", "economics", "finance",
    "information systems", "cybersecurity",
]


def _detect_degree(text: str) -> tuple[str, int]:
    """
    Detect degree level from text.

    Returns:
        Tuple of (degree_name, education_level_ordinal).
    """
    for degree_name, pattern in _DEGREE_PATTERNS.items():
        if pattern.search(text):
            level_map = {
                "phd": 4,
                "master": 3,
                "bachelor": 2,
                "diploma": 1,
                "high_school": 0,
            }
            return degree_name, level_map[degree_name]
    return "unknown", 0


def _extract_gpa(text: str) -> tuple[float, float]:
    """
    Extract GPA and normalize to 0-1 scale.

    Returns:
        Tuple of (raw_gpa, normalized_gpa).
    """
    # Try GPA/CGPA pattern
    match = _GPA_PATTERN.search(text)
    if match:
        gpa = float(match.group(1))
        scale = float(match.group(2)) if match.group(2) else 0

        if scale == 0:
            # Guess scale: if GPA > 5, likely out of 10; else out of 4
            scale = 10.0 if gpa > 5 else 4.0

        normalized = min(gpa / scale, 1.0)
        return gpa, normalized

    # Try percentage
    match = _PERCENTAGE_PATTERN.search(text)
    if match:
        pct = float(match.group(1))
        if 0 < pct <= 100:
            return pct, pct / 100.0

    return 0.0, 0.0


def _extract_major(text: str) -> str:
    """Extract field of study / major from education text."""
    text_lower = text.lower()

    # Try to find known majors
    for major in _MAJOR_KEYWORDS:
        if major in text_lower:
            return major.title()

    # Try pattern: "in {major}" or "of {major}"
    match = re.search(
        r"(?:in|of)\s+([A-Z][\w\s]+?)(?:\s*[-–,\n]|\s+(?:from|at|with)|\s*$)",
        text,
    )
    if match:
        major = match.group(1).strip()
        if 3 < len(major) < 60:
            return major

    return ""


def parse_education_section(text: str) -> list[dict]:
    """
    Parse the education section into structured entries.

    Each entry contains:
    - institution: University/college name
    - degree: Degree type (bachelor, master, phd, etc.)
    - degree_level: Integer ordinal (0-4)
    - major: Field of study
    - graduation_year: Year of graduation
    - gpa_raw: Raw GPA value
    - gpa_normalized: GPA normalized to 0-1
    - coursework: Relevant coursework if listed

    Args:
        text: Education section text content.

    Returns:
        List of education entry dictionaries.
    """
    if not text or not text.strip():
        return []

    entries: list[dict] = []
    lines = text.split("\n")
    current_entry: dict | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line contains a degree keyword (new entry signal)
        has_degree = any(pattern.search(stripped) for pattern in _DEGREE_PATTERNS.values())

        if has_degree:
            # Process previous entry
            if current_entry and current_lines:
                block_text = "\n".join(current_lines)
                _finalize_entry(current_entry, block_text)
                entries.append(current_entry)

            degree_name, degree_level = _detect_degree(stripped)
            current_entry = {
                "institution": "",
                "degree": degree_name,
                "degree_level": degree_level,
                "major": "",
                "graduation_year": "",
                "gpa_raw": 0.0,
                "gpa_normalized": 0.0,
                "coursework": [],
            }
            current_lines = [stripped]

        elif current_entry is not None:
            current_lines.append(stripped)
        else:
            # Before first degree — might be institution name
            current_entry = {
                "institution": stripped,
                "degree": "unknown",
                "degree_level": 0,
                "major": "",
                "graduation_year": "",
                "gpa_raw": 0.0,
                "gpa_normalized": 0.0,
                "coursework": [],
            }
            current_lines = [stripped]

    # Process last entry
    if current_entry and current_lines:
        block_text = "\n".join(current_lines)
        _finalize_entry(current_entry, block_text)
        entries.append(current_entry)

    logger.debug(f"Parsed {len(entries)} education entries")
    return entries


def _finalize_entry(entry: dict, block_text: str) -> None:
    """Fill in missing fields from the full block text."""
    # Institution (if not already set)
    if not entry["institution"]:
        # First line that looks like an institution name
        for line in block_text.split("\n"):
            line = line.strip()
            if (
                line
                and not any(p.search(line) for p in _DEGREE_PATTERNS.values())
                and not _GPA_PATTERN.search(line)
                and not _PERCENTAGE_PATTERN.search(line)
                and len(line) > 3
            ):
                entry["institution"] = line
                break

    # Major
    if not entry["major"]:
        entry["major"] = _extract_major(block_text)

    # GPA
    gpa_raw, gpa_norm = _extract_gpa(block_text)
    entry["gpa_raw"] = gpa_raw
    entry["gpa_normalized"] = gpa_norm

    # Graduation year
    years = _YEAR_PATTERN.findall(block_text)
    if years:
        # Take the latest year as graduation year
        [int(f"{y}") for y in years]
        # Actually reconstruct full years
        all_years = [int(m) for m in re.findall(r"\b(19\d{2}|20\d{2})\b", block_text)]
        if all_years:
            entry["graduation_year"] = str(max(all_years))

    # Coursework
    course_match = re.search(
        r"(?:coursework|courses|relevant\s+courses?)[\s:]+(.+)",
        block_text,
        re.IGNORECASE,
    )
    if course_match:
        courses = re.split(r"[,;|]", course_match.group(1))
        entry["coursework"] = [c.strip() for c in courses if c.strip()]
