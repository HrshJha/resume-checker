"""
Seniority level detection from job descriptions.

Uses keyword patterns and contextual signals to classify JD seniority
on a 0-6 scale: intern(0), junior(1), mid(2), senior(3), staff(4),
principal(5), architect/VP(6).
"""

from __future__ import annotations

import re

from src.utils.logger import get_logger

logger = get_logger("seniority_detector")

# Seniority keyword patterns (ordered by priority)
_SENIORITY_PATTERNS: list[tuple[int, list[re.Pattern]]] = [
    (0, [  # Intern
        re.compile(r"\bintern(ship)?\b", re.IGNORECASE),
        re.compile(r"\btrainee\b", re.IGNORECASE),
        re.compile(r"\bco-?op\b", re.IGNORECASE),
    ]),
    (1, [  # Junior
        re.compile(r"\bjunior\b", re.IGNORECASE),
        re.compile(r"\bentry[\s-]level\b", re.IGNORECASE),
        re.compile(r"\bassociate\s+(software|developer|engineer)\b", re.IGNORECASE),
        re.compile(r"\bgraduate\s+(software|developer|engineer)\b", re.IGNORECASE),
        re.compile(r"\b(0|1)[-–]\d+\s*years?\b", re.IGNORECASE),
    ]),
    (2, [  # Mid-level
        re.compile(r"\bmid[\s-]?level\b", re.IGNORECASE),
        re.compile(r"\b(2|3)[-–]\d+\s*years?\b", re.IGNORECASE),
        re.compile(r"\bsoftware\s+(engineer|developer)\s*(I{1,2}|1|2)?\b", re.IGNORECASE),
    ]),
    (3, [  # Senior
        re.compile(r"\bsenior\b", re.IGNORECASE),
        re.compile(r"\bsr\.?\b", re.IGNORECASE),
        re.compile(r"\b(5|6|7)[-–+]\d*\s*years?\b", re.IGNORECASE),
        re.compile(r"\bsoftware\s+(engineer|developer)\s*(III|3)\b", re.IGNORECASE),
    ]),
    (4, [  # Staff / Lead
        re.compile(r"\bstaff\b", re.IGNORECASE),
        re.compile(r"\b(tech)?\s*lead\b", re.IGNORECASE),
        re.compile(r"\b(8|9|10)[-–+]\d*\s*years?\b", re.IGNORECASE),
    ]),
    (5, [  # Principal / Director
        re.compile(r"\bprincipal\b", re.IGNORECASE),
        re.compile(r"\bdirector\b", re.IGNORECASE),
        re.compile(r"\bdistinguished\b", re.IGNORECASE),
        re.compile(r"\b1[0-5][-–+]\d*\s*years?\b", re.IGNORECASE),
    ]),
    (6, [  # Architect / VP / Fellow
        re.compile(r"\b(chief|head\s+of)\b", re.IGNORECASE),
        re.compile(r"\bvp\b", re.IGNORECASE),
        re.compile(r"\bvice\s+president\b", re.IGNORECASE),
        re.compile(r"\bfellow\b", re.IGNORECASE),
        re.compile(r"\b(chief|head)\s+(architect|technolog)", re.IGNORECASE),
    ]),
]


def detect_seniority(text: str, title: str = "") -> int:
    """
    Detect seniority level from JD text and title.

    Args:
        text: Full JD text.
        title: Job title (higher priority for detection).

    Returns:
        Integer seniority level (0-6).
    """
    # Check title first (higher priority)
    combined = f"{title}\n{text}"

    best_level = 2  # Default: mid-level
    best_priority = -1

    for level, patterns in _SENIORITY_PATTERNS:
        for pattern in patterns:
            # Title matches get higher priority
            if title and pattern.search(title):
                priority = level + 100  # Title match is decisive
                if priority > best_priority:
                    best_priority = priority
                    best_level = level

            elif pattern.search(combined):
                priority = level
                if priority > best_priority:
                    best_priority = priority
                    best_level = level

    logger.debug(f"Detected seniority: {best_level} (title: '{title}')")
    return best_level
