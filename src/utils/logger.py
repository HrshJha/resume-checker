"""
Structured logging with PII masking for the Candidate Intelligence System.

Uses Loguru for structured JSON logging. All log entries are scrubbed
of personally identifiable information (email, phone, address patterns)
before emission.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from loguru import logger
import loguru

# ---------------------------------------------------------------------------
# PII masking patterns
# ---------------------------------------------------------------------------
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL_REDACTED]"),
    # Phone numbers (various formats)
    (
        re.compile(
            r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
        ),
        "[PHONE_REDACTED]",
    ),
    # SSN-like patterns
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    # Street addresses (simplified)
    (
        re.compile(
            r"\d{1,5}\s+\w+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)\b",
            re.IGNORECASE,
        ),
        "[ADDRESS_REDACTED]",
    ),
]


def mask_pii(text: str) -> str:
    """Remove personally identifiable information from a text string."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _pii_filter(record: Any) -> bool:
    """Loguru filter that masks PII in log messages."""
    if isinstance(record, dict) and "message" in record:
        record["message"] = mask_pii(record["message"])
    return True


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

def setup_logger(
    level: str = "INFO",
    json_output: bool = False,
    log_file: str | None = None,
) -> None:
    """
    Configure the application logger.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, emit structured JSON logs.
        log_file: Optional file path for log output.
    """
    # Remove default handler
    logger.remove()

    # Determine format
    if json_output:
        fmt = (
            '{{"timestamp": "{time:YYYY-MM-DDTHH:mm:ss.SSSZ}", '
            '"level": "{level}", '
            '"module": "{module}", '
            '"function": "{function}", '
            '"line": {line}, '
            '"message": "{message}"}}'
        )
    else:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    # Console handler
    logger.add(
        sys.stderr,
        format=fmt,
        level=level,
        filter=_pii_filter,
        colorize=not json_output,
    )

    # Optional file handler
    if log_file:
        logger.add(
            log_file,
            format=fmt,
            level=level,
            filter=_pii_filter,
            rotation="50 MB",
            retention="7 days",
            compression="gz",
        )


def get_logger(name: str = "cis") -> Any:
    """Return a contextualized logger instance."""
    return logger.bind(context=name)
