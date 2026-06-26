"""
Skill extraction from job descriptions using NER + dictionary matching.

Extracts required skills, preferred skills, and soft skills from
structured JD sections with weighted importance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger
from src.utils.skill_canonicalizer import SkillCanonicalizer

logger = get_logger("skill_extractor")

# ---------------------------------------------------------------------------
# Soft skill patterns
# ---------------------------------------------------------------------------
SOFT_SKILL_PATTERNS: list[str] = [
    "communication", "teamwork", "leadership", "problem solving",
    "critical thinking", "time management", "adaptability",
    "collaboration", "creativity", "attention to detail",
    "analytical", "interpersonal", "organizational",
    "decision making", "project management", "mentoring",
    "coaching", "strategic thinking", "presentation",
    "negotiation", "conflict resolution", "empathy",
    "initiative", "self-motivated", "proactive",
    "multitasking", "cross-functional", "stakeholder management",
    "agile", "scrum", "fast-paced", "dynamic environment",
]

# Bullet point pattern
_BULLET_RE = re.compile(r"^[\s]*[-•●▪*][\s]+(.+)$", re.MULTILINE)


@dataclass
class ExtractedSkill:
    """A skill extracted from a JD."""
    name: str  # Canonical name
    raw_text: str  # Original text
    category: str  # "required", "preferred", "soft"
    confidence: float = 1.0
    source_section: str = ""


@dataclass
class SkillExtractionResult:
    """Result of skill extraction from a JD."""
    required_skills: list[ExtractedSkill] = field(default_factory=list)
    preferred_skills: list[ExtractedSkill] = field(default_factory=list)
    soft_skills: list[ExtractedSkill] = field(default_factory=list)
    all_skills: list[str] = field(default_factory=list)


def _extract_bullet_items(text: str) -> list[str]:
    """Extract bullet point items from text."""
    matches = _BULLET_RE.findall(text)
    if matches:
        return [m.strip() for m in matches]

    # Also try line-by-line for non-bulleted lists
    lines = text.split("\n")
    items = [line.strip() for line in lines if line.strip() and len(line.strip()) > 3]
    return items


def _extract_skills_from_text(
    text: str,
    canonicalizer: SkillCanonicalizer,
    category: str,
    section_name: str,
) -> list[ExtractedSkill]:
    """Extract and canonicalize skills from a text block."""
    skills: list[ExtractedSkill] = []
    seen: set[str] = set()

    # Extract from bullet items
    items = _extract_bullet_items(text)

    for item in items:
        # Try to find known skills in each item
        words = re.split(r"[,;/|]|\band\b|\bor\b", item)
        for word in words:
            word = word.strip().strip("()[].")
            if len(word) < 2 or len(word) > 50:
                continue

            canonical, conf = canonicalizer.canonicalize(word)
            if conf >= 0.7 and canonical.lower() not in seen:
                seen.add(canonical.lower())
                skills.append(
                    ExtractedSkill(
                        name=canonical,
                        raw_text=word,
                        category=category,
                        confidence=conf,
                        source_section=section_name,
                    )
                )

    return skills


def _extract_soft_skills(text: str) -> list[ExtractedSkill]:
    """Extract soft skills using pattern matching."""
    skills: list[ExtractedSkill] = []
    seen: set[str] = set()
    text_lower = text.lower()

    for skill in SOFT_SKILL_PATTERNS:
        if skill.lower() in text_lower and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(
                ExtractedSkill(
                    name=skill.title(),
                    raw_text=skill,
                    category="soft",
                    confidence=0.9,
                    source_section="full",
                )
            )

    return skills


def extract_skills(
    jd_sections: list[dict],
    full_text: str,
    canonicalizer: Optional[SkillCanonicalizer] = None,
) -> SkillExtractionResult:
    """
    Extract skills from parsed JD sections.

    Maps JD sections to skill categories:
    - "requirements" → required_skills
    - "preferred" → preferred_skills
    - Soft skills extracted from all text

    Args:
        jd_sections: List of {"name": str, "content": str} from JD parser.
        full_text: Full JD text for soft skill extraction.
        canonicalizer: Optional skill canonicalizer instance.

    Returns:
        SkillExtractionResult with categorized skills.
    """
    if canonicalizer is None:
        canonicalizer = SkillCanonicalizer()

    required: list[ExtractedSkill] = []
    preferred: list[ExtractedSkill] = []

    # Section-to-category mapping
    required_sections = {"requirements", "experience", "full"}
    preferred_sections = {"preferred"}

    for section in jd_sections:
        name = section.get("name", "") if isinstance(section, dict) else section.name
        content = section.get("content", "") if isinstance(section, dict) else section.content

        if name in required_sections:
            required.extend(
                _extract_skills_from_text(content, canonicalizer, "required", name)
            )
        elif name in preferred_sections:
            preferred.extend(
                _extract_skills_from_text(content, canonicalizer, "preferred", name)
            )
        else:
            # Responsibilities and other sections contribute to required
            skills = _extract_skills_from_text(content, canonicalizer, "required", name)
            required.extend(skills)

    # Extract soft skills from full text
    soft = _extract_soft_skills(full_text)

    # Deduplicate
    seen: set[str] = set()
    deduped_required = []
    for s in required:
        if s.name.lower() not in seen:
            seen.add(s.name.lower())
            deduped_required.append(s)

    deduped_preferred = []
    for s in preferred:
        if s.name.lower() not in seen:
            seen.add(s.name.lower())
            deduped_preferred.append(s)

    all_skills = [s.name for s in deduped_required + deduped_preferred + soft]

    logger.debug(
        f"Extracted skills: {len(deduped_required)} required, "
        f"{len(deduped_preferred)} preferred, {len(soft)} soft"
    )

    return SkillExtractionResult(
        required_skills=deduped_required,
        preferred_skills=deduped_preferred,
        soft_skills=soft,
        all_skills=all_skills,
    )
