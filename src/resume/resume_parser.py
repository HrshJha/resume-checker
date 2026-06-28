"""
Master resume parser — orchestrates the full parsing pipeline.

Pipeline: File detection → Parse → Section detect → Entity extract →
Date normalize → Skill canonicalize → Evidence link → Embed → Feature store
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.parser.pdf_parser import parse_pdf
from src.parser.docx_parser import parse_docx
from src.parser.ocr_parser import parse_scanned_pdf
from src.parser.section_detector import detect_sections, get_section_content
from src.resume.experience_parser import parse_experience_section
from src.resume.project_parser import parse_projects_section
from src.resume.education_parser import parse_education_section
from src.utils.file_validator import validate_file
from src.utils.logger import get_logger
from src.utils.skill_canonicalizer import SkillCanonicalizer
from src.utils.text_cleaner import clean_text
from src.utils.date_normalizer import parse_date, compute_total_experience_months

logger = get_logger("resume_parser")


@dataclass
class ResumeLinks:
    """Extracted links from a resume."""
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    kaggle: Optional[str] = None
    blog: Optional[str] = None
    other: list[str] = field(default_factory=list)


@dataclass
class ParsedResume:
    """Complete parsed resume data structure."""
    candidate_id: str
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    raw_skills: list[str] = field(default_factory=list)
    certifications: list[dict] = field(default_factory=list)
    links: Optional[ResumeLinks] = None
    experience_years: float = 0.0
    experience_metrics: dict[str, float] = field(default_factory=dict)
    page_count: int = 0
    word_count: int = 0
    warnings: list[str] = field(default_factory=list)
    parser_used: str = ""
    evidence_graph: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "candidate_id": self.candidate_id,
            "sections": self.sections,
            "experience": self.experience,
            "education": self.education,
            "projects": self.projects,
            "skills": self.skills,
            "raw_skills": self.raw_skills,
            "certifications": self.certifications,
            "links": {
                "github": self.links.github if self.links else None,
                "linkedin": self.links.linkedin if self.links else None,
                "portfolio": self.links.portfolio if self.links else None,
                "kaggle": self.links.kaggle if self.links else None,
                "blog": self.links.blog if self.links else None,
            },
            "experience_years": self.experience_years,
            "experience_metrics": self.experience_metrics,
            "page_count": self.page_count,
            "word_count": self.word_count,
            "warnings": self.warnings,
        }


def _extract_links(text: str) -> ResumeLinks:
    """Extract URLs from resume text."""
    import re

    links = ResumeLinks()
    url_pattern = re.compile(
        r'https?://[^\s<>"\')\]]+', re.IGNORECASE
    )
    urls = url_pattern.findall(text)

    for url in urls:
        url_lower = url.lower()
        if "github.com" in url_lower:
            links.github = url
        elif "linkedin.com" in url_lower:
            links.linkedin = url
        elif "kaggle.com" in url_lower:
            links.kaggle = url
        elif any(kw in url_lower for kw in ["medium.com", "blog", "dev.to", "hashnode"]):
            links.blog = url
        else:
            if not links.portfolio:
                links.portfolio = url
            else:
                links.other.append(url)

    return links


def _extract_skills_from_section(skills_text: str, canonicalizer: SkillCanonicalizer) -> tuple[list[str], list[str]]:
    """Extract and canonicalize skills from the skills section."""
    import re

    # Split on common delimiters
    raw_tokens = re.split(r"[,;|•●▪\n]", skills_text)
    raw_skills = [t.strip().strip("-•●▪ ") for t in raw_tokens if t.strip()]

    # Remove category headers (e.g., "Programming Languages:", "Databases:")
    filtered = []
    for skill in raw_skills:
        # If it ends with ":" it's likely a category header
        if skill.endswith(":"):
            continue
        # Split on ":" in case "Category: skill1, skill2"
        if ":" in skill:
            parts = skill.split(":", 1)
            sub_skills = re.split(r"[,;|]", parts[1])
            filtered.extend([s.strip() for s in sub_skills if s.strip()])
        else:
            if len(skill) > 1:
                filtered.append(skill)

    # Canonicalize
    canonical_skills = []
    seen: set[str] = set()
    for raw in filtered:
        canonical, conf = canonicalizer.canonicalize(raw)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            canonical_skills.append(canonical)

    return canonical_skills, filtered


def _extract_certifications(cert_text: str) -> list[dict]:
    """Extract certifications from the certifications section."""
    import re

    certs = []
    lines = cert_text.split("\n")

    for line in lines:
        line = line.strip().strip("-•●▪ ")
        if not line or len(line) < 5:
            continue

        cert = {"name": line, "provider": "", "date": ""}

        # Try to extract provider
        provider_patterns = [
            r"(?:from|by|issued by|provider:?)\s+(.+)",
            r"\((.+?)\)",
        ]
        for pattern in provider_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                cert["provider"] = match.group(1).strip()
                break

        # Try to extract date
        date_match = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}|\d{4})", line)
        if date_match:
            cert["date"] = date_match.group(1)

        certs.append(cert)

    return certs


def parse_resume(
    file_path: str | Path,
    candidate_id: Optional[str] = None,
    canonicalizer: Optional[SkillCanonicalizer] = None,
) -> ParsedResume:
    """
    Parse a resume file through the complete pipeline.

    Pipeline steps:
    1. File type detection + validation
    2. Text extraction (PDF/DOCX/OCR)
    3. Section detection
    4. Entity extraction per section
    5. Skill canonicalization
    6. Link extraction
    7. Evidence linking

    Args:
        file_path: Path to the resume file.
        candidate_id: Optional UUID; generated if not provided.
        canonicalizer: Optional skill canonicalizer instance.

    Returns:
        ParsedResume with all extracted data.
    """
    file_path = Path(file_path)
    if candidate_id is None:
        candidate_id = str(uuid.uuid4())
    if canonicalizer is None:
        canonicalizer = SkillCanonicalizer()

    warnings: list[str] = []

    # Step 1: Validate file
    file_type = validate_file(file_path)

    # Step 2: Extract text
    full_text = ""
    page_count = 0
    parser_used = ""

    if file_type == "pdf":
        pdf_result = parse_pdf(file_path)
        full_text = pdf_result.full_text
        page_count = pdf_result.page_count
        parser_used = pdf_result.parser_used
        warnings.extend(pdf_result.warnings)

        # If scanned, try OCR
        if pdf_result.is_scanned and not full_text.strip():
            logger.info(f"Attempting OCR for scanned PDF: {file_path.name}")
            ocr_result = parse_scanned_pdf(file_path)
            full_text = ocr_result.full_text
            page_count = ocr_result.page_count
            parser_used = "ocr"
            warnings.extend(ocr_result.warnings)

    elif file_type == "docx":
        docx_result = parse_docx(file_path)
        full_text = docx_result.full_text
        parser_used = "docx"
        warnings.extend(docx_result.warnings)

    # Clean text
    full_text = clean_text(full_text, strip_html_tags=True)
    word_count = len(full_text.split())

    # Step 3: Detect sections
    section_result = detect_sections(full_text)
    warnings.extend(section_result.warnings)

    sections: dict[str, str] = {}
    for sec in section_result.sections:
        sections[sec.name] = sec.content

    # Step 4: Extract entities per section

    # Experience
    experience = []
    exp_text = get_section_content(section_result, "experience")
    if exp_text:
        experience = parse_experience_section(exp_text)

    # Education
    education = []
    edu_text = get_section_content(section_result, "education")
    if edu_text:
        education = parse_education_section(edu_text)

    # Projects
    projects = []
    proj_text = get_section_content(section_result, "projects")
    if proj_text:
        projects = parse_projects_section(proj_text)

    # Skills - Extract from full text to avoid missing skills embedded in experience
    skills: list[str] = canonicalizer.extract_skills_from_text(full_text)
    raw_skills: list[str] = []
    
    # Also extract from explicitly defined skills section for raw tokens
    skills_text = get_section_content(section_result, "skills")
    if skills_text:
        section_skills, section_raw = _extract_skills_from_section(skills_text, canonicalizer)
        raw_skills = section_raw
        for s in section_skills:
            if s not in skills:
                skills.append(s)

    # Output Validation (Stage 9)
    if not skills:
        raise ValueError(
            f"Extraction Failed: Zero skills were extracted from resume {file_path.name}. "
            "Ensure the resume contains valid parseable text and recognizable technologies."
        )

    # Certifications
    certifications = []
    cert_text = get_section_content(section_result, "certifications")
    if cert_text:
        certifications = _extract_certifications(cert_text)

    # Step 5: Extract links
    links = _extract_links(full_text)

    # Step 6: Compute total experience years using interval union
    exp_ranges = []
    ranges_by_type: dict[str, list] = {
        "professional": [], "internship": [], "freelance": [], 
        "part-time": [], "research": []
    }
    
    for exp in experience:
        start = exp.get("start_date")
        end = exp.get("end_date")
        e_type = exp.get("entry_type", "professional")
        
        # Parse strings back to dates if they exist, else None
        s_date = parse_date(start) if start else None
        e_date = parse_date(end) if end else None
        
        if s_date or e_date:
            exp_ranges.append((s_date, e_date))
            if e_type in ranges_by_type:
                ranges_by_type[e_type].append((s_date, e_date))
            
    total_months = compute_total_experience_months(exp_ranges)
    total_exp_years = total_months / 12.0
    
    experience_metrics = {}
    for e_type, rngs in ranges_by_type.items():
        if rngs:
            experience_metrics[f"{e_type}_years"] = compute_total_experience_months(rngs) / 12.0
        else:
            experience_metrics[f"{e_type}_years"] = 0.0

    # Build evidence graph (skill → evidence sources)
    evidence_graph: dict[str, dict] = {}
    for skill in skills:
        skill_lower = skill.lower()
        evidence: dict[str, list[str]] = {
            "experience": [], "projects": [], "certifications": [],
        }

        for exp in experience:
            bullets = exp.get("bullets", [])
            for bullet in bullets:
                if skill_lower in bullet.lower():
                    evidence["experience"].append(exp.get("company", ""))
                    break

        for proj in projects:
            tech = proj.get("technologies", [])
            desc = proj.get("description", "")
            if skill_lower in " ".join(tech).lower() or skill_lower in desc.lower():
                evidence["projects"].append(proj.get("title", ""))

        for cert in certifications:
            if skill_lower in cert.get("name", "").lower():
                evidence["certifications"].append(cert.get("name", ""))

        if any(v for v in evidence.values()):
            evidence_graph[skill] = evidence

    logger.info(
        f"Parsed resume {file_path.name}: "
        f"{len(experience)} exp, {len(education)} edu, "
        f"{len(projects)} proj, {len(skills)} skills, "
        f"{total_exp_years:.1f} years"
    )

    return ParsedResume(
        candidate_id=candidate_id,
        full_text=full_text,
        sections=sections,
        experience=experience,
        education=education,
        projects=projects,
        skills=skills,
        raw_skills=raw_skills,
        certifications=certifications,
        links=links,
        experience_years=total_exp_years,
        experience_metrics=experience_metrics,
        page_count=page_count,
        word_count=word_count,
        warnings=warnings,
        parser_used=parser_used,
        evidence_graph=evidence_graph,
    )
