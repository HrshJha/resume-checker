"""
Domain classifier for job descriptions.

Classifies JDs into technology domains: backend, frontend, fullstack,
data_science, ml_ai, devops, mobile, embedded, security, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger("domain_classifier")

# Domain keyword dictionaries
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "backend": [
        "backend", "back-end", "server-side", "api", "microservices",
        "rest api", "graphql", "grpc", "database", "sql", "nosql",
        "distributed systems", "message queue", "kafka", "rabbitmq",
        "redis", "caching", "authentication", "authorization",
    ],
    "frontend": [
        "frontend", "front-end", "ui", "ux", "react", "angular", "vue",
        "html", "css", "javascript", "typescript", "web", "responsive",
        "accessibility", "a11y", "spa", "pwa", "dom", "webpack",
    ],
    "fullstack": [
        "full stack", "fullstack", "full-stack", "end-to-end",
    ],
    "data_science": [
        "data science", "data scientist", "analytics", "statistical",
        "a/b testing", "experimentation", "business intelligence",
        "data visualization", "tableau", "power bi", "jupyter",
        "pandas", "r programming", "statistics",
    ],
    "ml_ai": [
        "machine learning", "deep learning", "artificial intelligence",
        "nlp", "natural language", "computer vision", "recommendation",
        "neural network", "transformer", "bert", "gpt", "llm",
        "pytorch", "tensorflow", "model training", "mlops",
        "feature engineering", "reinforcement learning",
    ],
    "data_engineering": [
        "data engineering", "data pipeline", "etl", "elt", "data warehouse",
        "spark", "airflow", "dbt", "snowflake", "bigquery", "redshift",
        "data lake", "streaming", "batch processing", "data platform",
    ],
    "devops": [
        "devops", "sre", "site reliability", "infrastructure",
        "kubernetes", "docker", "terraform", "ansible", "ci/cd",
        "monitoring", "observability", "cloud infrastructure",
        "aws", "gcp", "azure", "linux", "networking",
    ],
    "mobile": [
        "mobile", "ios", "android", "swift", "kotlin", "react native",
        "flutter", "mobile app", "app development",
    ],
    "embedded": [
        "embedded", "firmware", "iot", "rtos", "microcontroller",
        "c programming", "hardware", "fpga", "signal processing",
    ],
    "security": [
        "security", "cybersecurity", "penetration testing", "encryption",
        "vulnerability", "compliance", "soc", "siem", "firewall",
        "identity", "access management",
    ],
    "qa": [
        "quality assurance", "qa", "testing", "test automation",
        "selenium", "cypress", "playwright", "test engineer",
    ],
    "product": [
        "product manager", "product management", "roadmap",
        "stakeholder", "user research", "product strategy",
    ],
}


@dataclass
class DomainClassificationResult:
    """Domain classification result."""
    primary_domain: str
    confidence: float
    domain_scores: dict[str, float]
    secondary_domains: list[str]


def classify_domain(text: str, title: str = "") -> DomainClassificationResult:
    """
    Classify the technology domain of a job description.

    Args:
        text: Full JD text.
        title: Job title (contributes with higher weight).

    Returns:
        DomainClassificationResult with primary and secondary domains.
    """
    combined = text.lower()
    title_lower = title.lower()

    scores: dict[str, float] = {}

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            # Title matches count 3x
            if keyword in title_lower:
                score += 3.0
            # Body matches
            count = len(re.findall(re.escape(keyword), combined))
            score += count * 1.0

        # Normalize by number of keywords
        scores[domain] = score / len(keywords) if keywords else 0.0

    # Sort by score
    sorted_domains = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary = sorted_domains[0][0] if sorted_domains else "general"
    primary_score = sorted_domains[0][1] if sorted_domains else 0.0

    # Check for fullstack override
    if (
        scores.get("fullstack", 0) > 0
        or (scores.get("frontend", 0) > 1 and scores.get("backend", 0) > 1)
    ):
        primary = "fullstack"
        primary_score = max(scores.get("fullstack", 0), primary_score)

    # Secondary domains (score > 50% of primary)
    threshold = primary_score * 0.5
    secondary = [
        d for d, s in sorted_domains[1:4]
        if s >= threshold and s > 0
    ]

    # Normalize confidence
    total_score = sum(s for _, s in sorted_domains)
    confidence = primary_score / total_score if total_score > 0 else 0.0

    logger.debug(f"Domain classification: {primary} (conf={confidence:.2f})")

    return DomainClassificationResult(
        primary_domain=primary,
        confidence=min(confidence, 1.0),
        domain_scores=scores,
        secondary_domains=secondary,
    )
