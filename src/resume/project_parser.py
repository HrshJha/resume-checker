"""
Project section parser — extracts project details and computes complexity.

Extracts: title, technology stack, description, impact metrics,
team size, deployment info, and computes a complexity score.
"""

from __future__ import annotations

import re

from src.utils.logger import get_logger

logger = get_logger("project_parser")

# Technology extraction pattern
_TECH_PATTERN = re.compile(
    r"\b(Python|Java|JavaScript|TypeScript|React|Angular|Vue|Node\.?js|"
    r"Docker|Kubernetes|AWS|GCP|Azure|PostgreSQL|MySQL|MongoDB|Redis|"
    r"Kafka|Spark|TensorFlow|PyTorch|FastAPI|Django|Flask|Spring|"
    r"GraphQL|REST|CI/CD|Jenkins|Git|Terraform|Go|Rust|Swift|Kotlin|"
    r"Elasticsearch|RabbitMQ|Nginx|Next\.?js|Express|C\+\+|C#|Ruby|"
    r"PHP|Scala|Haskell|R\b|MATLAB|Pandas|NumPy|scikit-learn|"
    r"OpenCV|Selenium|Cypress|Jest|Mocha|Pytest|JUnit|"
    r"Tableau|Power BI|Snowflake|BigQuery|Airflow|dbt|"
    r"Firebase|Supabase|Vercel|Netlify|Heroku|"
    r"gRPC|WebSocket|OAuth|JWT|Stripe|Twilio)\b",
    re.IGNORECASE,
)

# Impact metrics patterns
_METRIC_PATTERNS = [
    re.compile(r"(\d+[KkMm]?\+?)\s*users?", re.IGNORECASE),
    re.compile(r"(\d+\.?\d*)\s*%\s*(reduction|improvement|increase|decrease|faster)", re.IGNORECASE),
    re.compile(r"\$(\d+[KkMm]?)\s*(saved|reduction|revenue)", re.IGNORECASE),
    re.compile(r"(\d+\.?\d*)\s*x\s*(faster|improvement|speedup)", re.IGNORECASE),
    re.compile(r"latency.+?(\d+)\s*ms", re.IGNORECASE),
    re.compile(r"(\d+)\s*(requests?|rps|qps)\s*per\s*second", re.IGNORECASE),
]

# Complexity indicators
_COMPLEXITY_SIGNALS = {
    "distributed": ["distributed", "microservices", "event-driven", "message queue"],
    "deployment": ["docker", "kubernetes", "k8s", "ci/cd", "deployed", "production"],
    "testing": ["test", "testing", "unit test", "integration test", "e2e", "tdd"],
    "cloud": ["aws", "gcp", "azure", "cloud", "serverless", "lambda"],
    "security": ["authentication", "authorization", "oauth", "jwt", "encryption", "rbac"],
    "monitoring": ["monitoring", "logging", "observability", "prometheus", "grafana", "alerting"],
    "scalability": ["redis", "kafka", "load balancing", "caching", "cdn", "sharding"],
    "database": ["postgresql", "mysql", "mongodb", "dynamodb", "redis", "elasticsearch"],
}


def _compute_complexity_score(text: str, technologies: list[str]) -> float:
    """
    Compute project complexity score (0-10).

    Weighted sum of complexity signals found in text.
    """
    text_lower = text.lower()
    score = 0.0

    weights = {
        "distributed": 2.0,
        "deployment": 1.5,
        "testing": 1.0,
        "cloud": 1.5,
        "security": 1.5,
        "monitoring": 1.0,
        "scalability": 2.0,
        "database": 1.0,
    }

    for category, keywords in _COMPLEXITY_SIGNALS.items():
        for keyword in keywords:
            if keyword in text_lower:
                score += weights.get(category, 1.0)
                break  # Count each category once

    # Bonus for tech stack size
    tech_count = len(set(technologies))
    if tech_count >= 8:
        score += 2.0
    elif tech_count >= 5:
        score += 1.0

    return min(score, 10.0)


def _extract_impact_metrics(text: str) -> dict:
    """Extract quantifiable impact metrics from project text."""
    metrics: dict = {}

    for pattern in _METRIC_PATTERNS:
        match = pattern.search(text)
        if match:
            metrics[pattern.pattern[:30]] = match.group(0)

    return metrics


def _extract_team_size(text: str) -> int:
    """Try to extract team size from project description."""
    patterns = [
        re.compile(r"team\s+of\s+(\d+)", re.IGNORECASE),
        re.compile(r"(\d+)\s*[-–]\s*member\s+team", re.IGNORECASE),
        re.compile(r"(\d+)\s+developers?", re.IGNORECASE),
        re.compile(r"(\d+)\s+engineers?", re.IGNORECASE),
    ]

    for pattern in patterns:
        match = pattern.search(text)
        if match:
            size = int(match.group(1))
            if 1 <= size <= 100:
                return size

    return 0


def parse_projects_section(text: str) -> list[dict]:
    """
    Parse the projects section into structured entries.

    Each entry contains:
    - title: Project name
    - description: Project description
    - technologies: List of technologies used
    - team_size: Number of team members
    - impact_metrics: Quantifiable results
    - complexity_score: 0-10 complexity rating
    - has_deployment: Boolean
    - domain: Detected project domain

    Args:
        text: Projects section text content.

    Returns:
        List of project dictionaries.
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    projects: list[dict] = []
    current_project: dict | None = None
    current_desc_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Heuristic: project titles are typically short and may be bold
        is_title = (
            len(stripped) < 80
            and not stripped.startswith(("-", "•", "●", "▪", "*"))
            and not re.match(r"^\d+\.", stripped)
            and (stripped[0].isupper() or stripped.startswith(("[")))
        )

        # Check if this is a new project (title-like line)
        if is_title and len(stripped) > 3:
            # Save previous project
            if current_project:
                desc = "\n".join(current_desc_lines).strip()
                current_project["description"] = desc
                current_project["technologies"] = list(
                    set(_TECH_PATTERN.findall(desc + " " + current_project.get("title", "")))
                )
                current_project["team_size"] = _extract_team_size(desc)
                current_project["impact_metrics"] = _extract_impact_metrics(desc)
                current_project["complexity_score"] = _compute_complexity_score(
                    desc, current_project["technologies"]
                )
                current_project["has_deployment"] = any(
                    kw in desc.lower()
                    for kw in ["deployed", "production", "live", "hosted", "launched"]
                )
                projects.append(current_project)

            # Start new project
            # Clean title: remove links, brackets
            title = re.sub(r"\[(.+?)\]", r"\1", stripped)
            title = re.sub(r"\(https?://[^\)]+\)", "", title).strip()

            current_project = {"title": title}
            current_desc_lines = []

        elif current_project is not None:
            # Add to current project description
            bullet_text = re.sub(r"^[\s]*[-•●▪*][\s]+", "", stripped)
            current_desc_lines.append(bullet_text)

        else:
            # Before first project
            if len(stripped) > 3:
                current_project = {"title": stripped}
                current_desc_lines = []

    # Don't forget last project
    if current_project:
        desc = "\n".join(current_desc_lines).strip()
        current_project["description"] = desc
        current_project["technologies"] = list(
            set(_TECH_PATTERN.findall(desc + " " + current_project.get("title", "")))
        )
        current_project["team_size"] = _extract_team_size(desc)
        current_project["impact_metrics"] = _extract_impact_metrics(desc)
        current_project["complexity_score"] = _compute_complexity_score(
            desc, current_project["technologies"]
        )
        current_project["has_deployment"] = any(
            kw in desc.lower()
            for kw in ["deployed", "production", "live", "hosted", "launched"]
        )
        projects.append(current_project)

    logger.debug(f"Parsed {len(projects)} projects")
    return projects
