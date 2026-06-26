"""
Experience section parser — extracts work history entries.

Extracts: company, role/title, dates, duration, bullet points,
technologies mentioned.
"""

from __future__ import annotations

import re
from typing import Optional

from src.utils.date_normalizer import parse_date_range, compute_duration_months, format_date
from src.utils.logger import get_logger

logger = get_logger("experience_parser")

# Date range pattern in experience entries
_DATE_LINE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}"
    r"|(?:\d{1,2}[/\-.]\d{4})"
    r"|(?:\d{4}[/\-.]\d{1,2})"
    r"|(?:\d{4}))"
    r"\s*[-–—~to]+\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}"
    r"|(?:\d{1,2}[/\-.]\d{4})"
    r"|(?:\d{4}[/\-.]\d{1,2})"
    r"|(?:\d{4})"
    r"|Present|Current|Now|Ongoing)",
    re.IGNORECASE,
)

# Bullet point pattern
_BULLET_RE = re.compile(r"^[\s]*[-•●▪*◦][\s]+", re.MULTILINE)

# Technology mention patterns
_TECH_EXTRACT_RE = re.compile(
    r"\b(Python|Java|JavaScript|TypeScript|React|Angular|Vue|Node\.?js|"
    r"Docker|Kubernetes|AWS|GCP|Azure|PostgreSQL|MySQL|MongoDB|Redis|"
    r"Kafka|Spark|TensorFlow|PyTorch|FastAPI|Django|Flask|Spring|"
    r"GraphQL|REST|CI/CD|Jenkins|Git|Linux|Terraform|Ansible|"
    r"Elasticsearch|RabbitMQ|Nginx|Go|Rust|Swift|Kotlin|"
    r"Microservices|Machine Learning|Deep Learning|NLP|"
    r"Tableau|Power BI|Snowflake|BigQuery|Airflow|dbt)\b",
    re.IGNORECASE,
)


def _is_role_line(line: str) -> bool:
    """Check if a line likely contains a job role/title."""
    role_keywords = [
        "engineer", "developer", "manager", "director", "lead",
        "architect", "analyst", "scientist", "designer", "consultant",
        "specialist", "coordinator", "intern", "associate", "senior",
        "principal", "staff", "head", "vp", "chief", "officer",
        "administrator", "devops", "sre", "qa", "tester",
    ]
    line_lower = line.lower()
    return any(kw in line_lower for kw in role_keywords)


def _is_company_line(line: str) -> bool:
    """Check if a line likely contains a company name."""
    # Company lines are typically short and may include location
    if len(line) > 100:
        return False
    # Common patterns: "Company Name | Location" or "Company Name, Location"
    if re.search(r"[|,]\s*(remote|hybrid)", line, re.IGNORECASE):
        return True
    if re.search(r",\s*[A-Z]{2}\b", line):  # State abbreviation
        return True
    return False


def parse_experience_section(text: str) -> list[dict]:
    """
    Parse the experience section into structured entries.

    Each entry contains:
    - company: Company name
    - role: Job title
    - start_date: YYYY-MM format
    - end_date: YYYY-MM format
    - duration_months: Float
    - bullets: List of achievement/responsibility strings
    - technologies: List of technologies mentioned

    Args:
        text: Experience section text content.

    Returns:
        List of experience entry dictionaries.
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    entries: list[dict] = []
    current_entry: Optional[dict] = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for date range (strong signal for new entry)
        date_match = _DATE_LINE_RE.search(stripped)

        if date_match:
            # Start a new entry
            if current_entry:
                entries.append(current_entry)

            start_date, end_date = parse_date_range(
                f"{date_match.group(1)} - {date_match.group(2)}"
            )
            duration = compute_duration_months(start_date, end_date)

            # Extract role/company from the same or adjacent lines
            date_text = date_match.group(0)
            remaining = stripped.replace(date_text, "").strip().strip("|,–-").strip()

            current_entry = {
                "company": "",
                "role": "",
                "start_date": format_date(start_date),
                "end_date": format_date(end_date),
                "duration_months": duration or 0,
                "bullets": [],
                "technologies": [],
            }

            if remaining:
                if _is_role_line(remaining):
                    current_entry["role"] = remaining
                else:
                    current_entry["company"] = remaining

        elif current_entry is not None:
            # Determine if this is a role, company, or bullet
            is_bullet = bool(_BULLET_RE.match(line))

            if is_bullet:
                bullet_text = _BULLET_RE.sub("", line).strip()
                if bullet_text:
                    current_entry["bullets"].append(bullet_text)
                    # Extract technologies from bullets
                    techs = _TECH_EXTRACT_RE.findall(bullet_text)
                    current_entry["technologies"].extend(techs)
            elif not current_entry["role"] and _is_role_line(stripped):
                current_entry["role"] = stripped
            elif not current_entry["company"]:
                current_entry["company"] = stripped
            else:
                # Treat as a bullet without prefix
                if len(stripped) > 20:
                    current_entry["bullets"].append(stripped)
                    techs = _TECH_EXTRACT_RE.findall(stripped)
                    current_entry["technologies"].extend(techs)

        elif not current_entry:
            # Before first date — might be role/company header
            if _is_role_line(stripped) or _is_company_line(stripped):
                current_entry = {
                    "company": "",
                    "role": stripped if _is_role_line(stripped) else "",
                    "start_date": "",
                    "end_date": "",
                    "duration_months": 0,
                    "bullets": [],
                    "technologies": [],
                }
                if not _is_role_line(stripped):
                    current_entry["company"] = stripped

    # Don't forget the last entry
    if current_entry:
        entries.append(current_entry)

    # Deduplicate technologies per entry
    for entry in entries:
        entry["technologies"] = list(set(entry["technologies"]))

    logger.debug(f"Parsed {len(entries)} experience entries")
    return entries
