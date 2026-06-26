"""
Unit tests for parsing, skill extraction, and section detection.
"""

from src.utils.text_cleaner import clean_text, normalize_unicode, strip_html
from src.utils.date_normalizer import parse_date, compute_duration_months, parse_date_range
from src.utils.skill_canonicalizer import SkillCanonicalizer
from src.parser.section_detector import detect_sections, _is_section_header
from src.jd.jd_parser import parse_jd
from src.jd.seniority_detector import detect_seniority
from src.jd.domain_classifier import classify_domain
from src.jd.skill_extractor import extract_skills


# ============================================================
# Text Cleaner Tests
# ============================================================

class TestTextCleaner:
    def test_normalize_unicode(self):
        text = "café"
        result = normalize_unicode(text)
        assert result == "café"

    def test_strip_html(self):
        text = "<p>Hello <b>World</b></p>"
        result = strip_html(text)
        assert "Hello" in result
        assert "<p>" not in result

    def test_clean_text_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""  # type: ignore

    def test_clean_text_whitespace(self):
        text = "  hello    world  \n\n\n\n\ntest  "
        result = clean_text(text)
        assert "hello world" in result


# ============================================================
# Date Normalizer Tests
# ============================================================

class TestDateNormalizer:
    def test_parse_month_year(self):
        d = parse_date("Jan 2022")
        assert d is not None
        assert d.year == 2022
        assert d.month == 1

    def test_parse_full_month(self):
        d = parse_date("January 2022")
        assert d is not None
        assert d.year == 2022

    def test_parse_numeric(self):
        d = parse_date("01/2022")
        assert d is not None
        assert d.month == 1

    def test_parse_iso(self):
        d = parse_date("2022-01")
        assert d is not None
        assert d.year == 2022

    def test_parse_present(self):
        from datetime import date
        d = parse_date("Present")
        assert d is not None
        assert d.year == date.today().year

    def test_parse_bare_year(self):
        d = parse_date("2022")
        assert d is not None
        assert d.year == 2022

    def test_duration_months(self):
        from datetime import date
        start = date(2020, 1, 1)
        end = date(2022, 6, 1)
        duration = compute_duration_months(start, end)
        assert duration == 29.0

    def test_parse_date_range(self):
        start, end = parse_date_range("Jan 2020 - Dec 2022")
        assert start is not None
        assert end is not None
        assert start.year == 2020
        assert end.year == 2022


# ============================================================
# Skill Canonicalizer Tests
# ============================================================

class TestSkillCanonicalizer:
    def setup_method(self):
        self.canonicalizer = SkillCanonicalizer()

    def test_exact_match(self):
        name, conf = self.canonicalizer.canonicalize("JS")
        assert name == "JavaScript"
        assert conf == 1.0

    def test_k8s(self):
        name, conf = self.canonicalizer.canonicalize("k8s")
        assert name == "Kubernetes"

    def test_postgres(self):
        name, conf = self.canonicalizer.canonicalize("Postgres")
        assert name == "PostgreSQL"

    def test_case_insensitive(self):
        name, conf = self.canonicalizer.canonicalize("python")
        assert name == "Python"

    def test_unknown_skill(self):
        name, conf = self.canonicalizer.canonicalize("SomeUnknownTech2024")
        assert isinstance(name, str)

    def test_batch(self):
        results = self.canonicalizer.canonicalize_batch(["JS", "k8s", "python"])
        assert len(results) == 3
        assert results[0][0] == "JavaScript"


# ============================================================
# Section Detection Tests
# ============================================================

class TestSectionDetector:
    def test_detect_education(self):
        result = _is_section_header("Education")
        assert result == "education"

    def test_detect_experience(self):
        result = _is_section_header("Work Experience")
        assert result == "experience"

    def test_detect_skills(self):
        result = _is_section_header("Technical Skills")
        assert result == "skills"

    def test_detect_projects(self):
        result = _is_section_header("Projects")
        assert result == "projects"

    def test_not_header(self):
        result = _is_section_header("This is a regular sentence about my work")
        assert result is None

    def test_full_detection(self, sample_resume_text):
        result = detect_sections(sample_resume_text)
        section_names = [s.name for s in result.sections]
        assert "experience" in section_names
        assert "education" in section_names
        assert "skills" in section_names


# ============================================================
# JD Parser Tests
# ============================================================

class TestJDParser:
    def test_parse_jd(self, sample_jd_text):
        result = parse_jd(sample_jd_text)
        assert result.cleaned_text
        assert result.title

    def test_experience_range(self, sample_jd_text):
        result = parse_jd(sample_jd_text)
        assert result.experience_min_years == 5.0


# ============================================================
# Seniority Detection Tests
# ============================================================

class TestSeniorityDetector:
    def test_senior(self):
        level = detect_seniority("", title="Senior Backend Engineer")
        assert level == 3

    def test_junior(self):
        level = detect_seniority("", title="Junior Developer")
        assert level == 1

    def test_intern(self):
        level = detect_seniority("", title="Software Engineering Intern")
        assert level == 0


# ============================================================
# Domain Classifier Tests
# ============================================================

class TestDomainClassifier:
    def test_backend_domain(self, sample_jd_text):
        result = classify_domain(sample_jd_text, title="Senior Backend Engineer")
        assert result.primary_domain == "backend"

    def test_ml_domain(self):
        text = "machine learning deep learning tensorflow pytorch NLP"
        result = classify_domain(text, title="ML Engineer")
        assert result.primary_domain == "ml_ai"


# ============================================================
# Skill Extractor Tests
# ============================================================

class TestSkillExtractor:
    def test_extract_from_jd(self, sample_jd_text):
        parsed = parse_jd(sample_jd_text)
        sections_as_dicts = [{"name": s.name, "content": s.content} for s in parsed.sections]
        result = extract_skills(sections_as_dicts, parsed.cleaned_text)
        assert len(result.required_skills) > 0 or len(result.all_skills) > 0
