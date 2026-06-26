"""
Text cleaning utilities for resume and JD preprocessing.

Handles Unicode normalization, whitespace cleanup, boilerplate removal,
abbreviation expansion, and HTML/script stripping.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Abbreviation expansion dictionary
# ---------------------------------------------------------------------------
ABBREVIATIONS: dict[str, str] = {
    "JS": "JavaScript",
    "TS": "TypeScript",
    "ML": "Machine Learning",
    "AI": "Artificial Intelligence",
    "DL": "Deep Learning",
    "NLP": "Natural Language Processing",
    "CV": "Computer Vision",
    "DS": "Data Science",
    "DE": "Data Engineering",
    "BE": "Backend",
    "FE": "Frontend",
    "FS": "Full Stack",
    "DB": "Database",
    "OS": "Operating System",
    "CI": "Continuous Integration",
    "CD": "Continuous Deployment",
    "QA": "Quality Assurance",
    "PM": "Project Management",
    "UI": "User Interface",
    "UX": "User Experience",
    "API": "Application Programming Interface",
    "SDK": "Software Development Kit",
    "SRE": "Site Reliability Engineering",
    "DevOps": "Development Operations",
    "k8s": "Kubernetes",
    "K8s": "Kubernetes",
    "AWS": "Amazon Web Services",
    "GCP": "Google Cloud Platform",
    "OOP": "Object-Oriented Programming",
}

# ---------------------------------------------------------------------------
# Boilerplate patterns (JD-specific noise)
# ---------------------------------------------------------------------------
_BOILERPLATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(equal\s+opportunity\s+employer|EEO\s+statement|"
        r"we\s+are\s+an?\s+equal\s+opportunity|"
        r"affirmative\s+action)",
        re.IGNORECASE,
    ),
    re.compile(r"(apply\s+now|click\s+here\s+to\s+apply|submit\s+your\s+application)", re.IGNORECASE),
    re.compile(r"(salary\s+range|compensation\s+package|pay\s+range)[\s:]*[\$€£]?\s*[\d,]+", re.IGNORECASE),
    re.compile(r"(visit\s+our\s+website|learn\s+more\s+at|for\s+more\s+information\s+visit)", re.IGNORECASE),
    re.compile(r"(disclaimer|privacy\s+policy|terms\s+and\s+conditions)", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# HTML / script removal
# ---------------------------------------------------------------------------
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)

# ---------------------------------------------------------------------------
# Whitespace patterns
# ---------------------------------------------------------------------------
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def normalize_unicode(text: str) -> str:
    """Apply NFC Unicode normalization."""
    return unicodedata.normalize("NFC", text)


def strip_html(text: str) -> str:
    """Remove HTML tags, <script>, and <style> blocks."""
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _HTML_TAG_RE.sub(" ", text)
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/tabs to single space, limit newlines."""
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def remove_boilerplate(text: str) -> str:
    """Remove common JD boilerplate patterns (EEO, Apply Now, etc.)."""
    lines = text.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        is_boilerplate = False
        for pattern in _BOILERPLATE_PATTERNS:
            if pattern.search(line):
                is_boilerplate = True
                break
        if not is_boilerplate:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def expand_abbreviations(text: str) -> str:
    """
    Expand common abbreviations in text.

    Only expands standalone abbreviations (whole-word match) to avoid
    corrupting longer tokens that happen to contain the abbreviation.
    """
    for abbr, expansion in ABBREVIATIONS.items():
        pattern = re.compile(rf"\b{re.escape(abbr)}\b")
        text = pattern.sub(expansion, text)
    return text


def clean_text(
    text: str,
    *,
    strip_html_tags: bool = True,
    remove_jd_boilerplate: bool = False,
    do_expand_abbreviations: bool = False,
) -> str:
    """
    Full text cleaning pipeline.

    Args:
        text: Raw input text.
        strip_html_tags: Remove HTML tags and script/style blocks.
        remove_jd_boilerplate: Remove EEO/Apply Now/salary boilerplate.
        do_expand_abbreviations: Expand common abbreviations.

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""

    text = normalize_unicode(text)

    if strip_html_tags:
        text = strip_html(text)

    if remove_jd_boilerplate:
        text = remove_boilerplate(text)

    if do_expand_abbreviations:
        text = expand_abbreviations(text)

    text = normalize_whitespace(text)
    return text
