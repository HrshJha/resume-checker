"""
Date parsing and normalization utilities for resume processing.

Handles diverse date formats found in resumes (e.g., "Jan 2022",
"January 2022", "01/2022", "2022-01", "Present/Current") and normalizes
them to YYYY-MM format. Computes duration in months between date pairs.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("date_normalizer")

# ---------------------------------------------------------------------------
# Regex patterns for date extraction
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# "Present", "Current", "Now", "Ongoing"
_PRESENT_KEYWORDS = {"present", "current", "now", "ongoing", "till date", "today"}

# Pattern: "Jan 2022" or "January 2022"
_MONTH_YEAR_RE = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES.keys()) + r")\s*,?\s*(\d{4})\b",
    re.IGNORECASE,
)

# Pattern: "01/2022" or "1/2022"
_NUMERIC_MONTH_YEAR_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{4})\b")

# Pattern: "2022-01" (ISO-like)
_ISO_MONTH_RE = re.compile(r"\b(\d{4})[/\-.](\d{1,2})\b")

# Pattern: bare year "2022"
_BARE_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# Date range pattern: "Jan 2020 - Present" or "Jan 2020 – Dec 2022"
_DATE_RANGE_RE = re.compile(
    r"(.+?)\s*[-–—~to]+\s*(.+)",
    re.IGNORECASE,
)


def _is_present(text: str) -> bool:
    """Check if text indicates the current date."""
    return text.strip().lower() in _PRESENT_KEYWORDS


def parse_date(text: str) -> Optional[date]:
    """
    Parse a date string into a ``datetime.date`` (day=1).

    Supported formats:
        - "Jan 2022", "January 2022"
        - "01/2022", "1-2022"
        - "2022-01", "2022/01"
        - "Present" / "Current" → today
        - "2022" (bare year → January of that year)

    Returns:
        ``date`` object or ``None`` if parsing fails.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Handle "Present" / "Current"
    if _is_present(cleaned):
        return date.today().replace(day=1)

    # Try "Month Year" pattern
    match = _MONTH_YEAR_RE.search(cleaned)
    if match:
        month_str = match.group(1).lower()
        year = int(match.group(2))
        month = _MONTH_NAMES.get(month_str, 1)
        try:
            return date(year, month, 1)
        except ValueError:
            pass

    # Try "MM/YYYY" pattern
    match = _NUMERIC_MONTH_YEAR_RE.search(cleaned)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12 and 1950 <= year <= 2100:
            try:
                return date(year, month, 1)
            except ValueError:
                pass

    # Try "YYYY-MM" ISO-like pattern
    match = _ISO_MONTH_RE.search(cleaned)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12 and 1950 <= year <= 2100:
            try:
                return date(year, month, 1)
            except ValueError:
                pass

    # Try bare year
    match = _BARE_YEAR_RE.search(cleaned)
    if match:
        year = int(match.group(0))
        if 1950 <= year <= 2100:
            return date(year, 1, 1)

    logger.debug(f"Could not parse date: '{cleaned}'")
    return None


def compute_duration_months(
    start: Optional[date], end: Optional[date]
) -> Optional[float]:
    """
    Compute duration in months between two dates.

    Returns:
        Number of months (float) or None if either date is missing.
    """
    if start is None or end is None:
        return None
    if end < start:
        # Swap if reversed (common data quality issue)
        start, end = end, start
    delta_months = (end.year - start.year) * 12 + (end.month - start.month)
    return max(0.0, float(delta_months))


def parse_date_range(text: str) -> tuple[Optional[date], Optional[date]]:
    """
    Parse a date range string like "Jan 2020 - Dec 2022" or "2019 - Present".

    Returns:
        Tuple of (start_date, end_date). Either may be ``None``.
    """
    if not text:
        return None, None

    match = _DATE_RANGE_RE.match(text.strip())
    if match:
        start_text = match.group(1).strip()
        end_text = match.group(2).strip()
        return parse_date(start_text), parse_date(end_text)

    # Single date (no range separator)
    single = parse_date(text)
    return single, None


def format_date(d: Optional[date]) -> str:
    """Format a date as YYYY-MM string."""
    if d is None:
        return ""
    return d.strftime("%Y-%m")


def check_date_overlap(
    ranges: list[tuple[Optional[date], Optional[date]]],
) -> list[tuple[int, int]]:
    """
    Detect overlapping date ranges.

    Args:
        ranges: List of (start, end) date tuples.

    Returns:
        List of (index_a, index_b) pairs that overlap.
    """
    overlaps: list[tuple[int, int]] = []
    valid = [
        (i, s, e)
        for i, (s, e) in enumerate(ranges)
        if s is not None and e is not None
    ]
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            _, s1, e1 = valid[i]
            _, s2, e2 = valid[j]
            if s1 <= e2 and s2 <= e1:
                overlaps.append((valid[i][0], valid[j][0]))
    return overlaps
