"""
Skill canonicalization using ESCO/O*NET ontology and fuzzy matching.

Maps raw skill tokens from resumes to canonical skill names using:
1. Direct lookup in synonym dictionary
2. Fuzzy string matching via rapidfuzz (threshold=85)
3. ESCO/O*NET ontology ID resolution
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

from src.utils.logger import get_logger

logger = get_logger("skill_canonicalizer")

# Global NLP model cache
_nlp = None

def _get_nlp():
    """Load spaCy NLP model for NER and phrase detection."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            logger.info("Loading spaCy model en_core_web_sm...")
            _nlp = spacy.load("en_core_web_sm", disable=["ner"])
        except Exception as e:
            logger.warning(f"Failed to load spaCy model: {e}")
            _nlp = False # False means tried and failed
    return _nlp if _nlp is not False else None


# ---------------------------------------------------------------------------
# Common synonym mappings (loaded eagerly)
# ---------------------------------------------------------------------------
_SYNONYM_MAP: dict[str, str] = {
    # JavaScript ecosystem
    "js": "JavaScript",
    "javascript": "JavaScript",
    "java script": "JavaScript",
    "ecmascript": "JavaScript",
    "es6": "JavaScript",
    "es2015": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "express": "Express.js",
    "expressjs": "Express.js",

    # Python ecosystem
    "python": "Python",
    "python3": "Python",
    "py": "Python",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    "pytorch": "PyTorch",
    "pytorch lightning": "PyTorch",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "keras": "Keras",
    "scikit-learn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "matplotlib": "Matplotlib",

    # Databases
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "pg": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "es": "Elasticsearch",
    "dynamodb": "DynamoDB",
    "cassandra": "Apache Cassandra",
    "sqlite": "SQLite",
    "mssql": "Microsoft SQL Server",
    "sql server": "Microsoft SQL Server",

    # Cloud & DevOps
    "aws": "Amazon Web Services",
    "amazon web services": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "docker": "Docker",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI/CD",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",

    # Languages
    "java": "Java",
    "c++": "C++",
    "cpp": "C++",
    "c plus plus": "C++",
    "c#": "C#",
    "csharp": "C#",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "scala": "Scala",
    "r": "R",
    "php": "PHP",

    # Data & ML
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "computer vision": "Computer Vision",
    "cv": "Computer Vision",
    "data science": "Data Science",
    "data engineering": "Data Engineering",
    "apache spark": "Apache Spark",
    "spark": "Apache Spark",
    "pyspark": "Apache Spark",
    "hadoop": "Apache Hadoop",
    "kafka": "Apache Kafka",
    "airflow": "Apache Airflow",
    "flink": "Apache Flink",

    # Tools
    "git": "Git",
    "github": "GitHub",
    "git hub": "GitHub",
    "gitlab": "GitLab",
    "jira": "Jira",
    "confluence": "Confluence",
    "linux": "Linux",
    "unix": "Unix",
    "bash": "Bash",
    "shell": "Shell Scripting",
    "powershell": "PowerShell",
    "vim": "Vim",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",

    # Messaging & APIs
    "rest": "REST API",
    "rest api": "REST API",
    "rest apis": "REST API",
    "restful": "REST API",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "websocket": "WebSocket",
    "rabbitmq": "RabbitMQ",

    # Monitoring
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
    "new relic": "New Relic",
    "elk": "ELK Stack",
    "splunk": "Splunk",
}


class SkillCanonicalizer:
    """
    Canonicalizes raw skill tokens to standard names.

    Resolution order:
    1. Direct synonym lookup (case-insensitive)
    2. Fuzzy match against canonical names (threshold=85)
    3. Return original if no match found
    """

    def __init__(
        self,
        ontology_path: Optional[str] = None,
        tech_ontology_path: Optional[str] = None,
        fuzzy_threshold: int = 85,
    ) -> None:
        self.fuzzy_threshold = fuzzy_threshold
        self._synonym_map: dict[str, str] = dict(_SYNONYM_MAP)
        self._canonical_names: list[str] = []
        self._ontology_ids: dict[str, str] = {}

        # Load ontology files if provided
        if ontology_path and Path(ontology_path).exists():
            self._load_ontology(ontology_path)
        if tech_ontology_path and Path(tech_ontology_path).exists():
            self._load_tech_ontology(tech_ontology_path)

        # Build canonical name list for fuzzy matching
        self._canonical_names = sorted(set(self._synonym_map.values()))

    def _load_ontology(self, path: str) -> None:
        """Load ESCO-style ontology JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for skill_id, skill_data in data.items():
                    if isinstance(skill_data, dict):
                        name = skill_data.get("name", "")
                        if name:
                            self._synonym_map[name.lower()] = name
                            self._ontology_ids[name] = skill_id
                            # Add alt labels
                            for alt in skill_data.get("alt_labels", []):
                                self._synonym_map[alt.lower()] = name
            logger.info(f"Loaded ESCO ontology with {len(data)} entries from {path}")
        except Exception as e:
            logger.warning(f"Failed to load ontology from {path}: {e}")

    def _load_tech_ontology(self, path: str) -> None:
        """Load technology ontology JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for category, skills in data.items():
                    if isinstance(skills, list):
                        for skill in skills:
                            if isinstance(skill, str):
                                self._synonym_map[skill.lower()] = skill
                            elif isinstance(skill, dict):
                                name = skill.get("name", "")
                                if name:
                                    self._synonym_map[name.lower()] = name
                                    for alias in skill.get("aliases", []):
                                        self._synonym_map[alias.lower()] = name
            logger.info(f"Loaded tech ontology from {path}")
        except Exception as e:
            logger.warning(f"Failed to load tech ontology from {path}: {e}")

    def canonicalize(self, raw_skill: str) -> tuple[str, float]:
        """
        Canonicalize a single skill token.

        Args:
            raw_skill: Raw skill string from resume.

        Returns:
            Tuple of (canonical_name, confidence_score).
            Confidence is 1.0 for exact match, 0.0-1.0 for fuzzy match.
        """
        if not raw_skill or not raw_skill.strip():
            return raw_skill, 0.0

        normalized = raw_skill.strip().lower()

        # Step 1: Direct lookup
        if normalized in self._synonym_map:
            return self._synonym_map[normalized], 1.0

        # Step 2: Fuzzy match
        if self._canonical_names:
            result = process.extractOne(
                normalized,
                self._canonical_names,
                scorer=fuzz.WRatio,
                score_cutoff=self.fuzzy_threshold,
            )
            if result:
                match_name, score, _ = result
                return match_name, score / 100.0

        # Step 3: No match — return original with title case
        return raw_skill.strip().title(), 0.0

    def canonicalize_batch(
        self, skills: list[str]
    ) -> list[tuple[str, float]]:
        """Canonicalize a list of skill tokens."""
        return [self.canonicalize(s) for s in skills]

    def get_ontology_id(self, canonical_name: str) -> Optional[str]:
        """Get the ESCO/ontology ID for a canonical skill name."""
        return self._ontology_ids.get(canonical_name)

    def get_canonical_names(self) -> list[str]:
        """Return all known canonical skill names."""
        return list(self._canonical_names)

    def extract_skills_from_text(self, text: str) -> list[str]:
        """
        Extract all known skills from a large body of text using regex word boundaries
        and spaCy-based Phrase Detection/NER for unknown proper nouns.
        Returns a deduplicated list of canonical skill names.
        """
        import re
        if not text:
            return []
            
        extracted_canonical = set()
        
        # 1. Dictionary Matching (Highest Confidence)
        text_lower = text.lower()
        sorted_synonyms = sorted(self._synonym_map.keys(), key=len, reverse=True)
        
        for synonym in sorted_synonyms:
            if len(synonym) < 2 and synonym not in ["c", "r"]:
                continue
                
            escaped_synonym = re.escape(synonym)
            if re.search(r'(?<![a-z0-9])' + escaped_synonym + r'(?![a-z0-9])', text_lower):
                canonical = self._synonym_map[synonym]
                extracted_canonical.add(canonical)
                # Remove matched known skills so NER doesn't duplicate them
                text_lower = re.sub(r'(?<![a-z0-9])' + escaped_synonym + r'(?![a-z0-9])', ' ', text_lower)
                
        # 2. Phrase Detection & POS Tagging (spaCy) for Unknown Skills
        nlp = _get_nlp()
        if nlp:
            # We process the original text (cased) to detect Proper Nouns
            doc = nlp(text)
            
            # Extract consecutive PROPN (Proper Nouns) as potential skills
            current_propn = []
            potential_skills = set()
            
            for token in doc:
                if token.pos_ == "PROPN" and len(token.text) > 1:
                    current_propn.append(token.text)
                else:
                    if current_propn:
                        phrase = " ".join(current_propn)
                        # Filter out common false positives and ensure it's not just regular words
                        if len(phrase) > 2 and phrase.lower() not in self._synonym_map:
                            potential_skills.add(phrase)
                        current_propn = []
                        
            # If a potential skill appears more than once or looks like a tech acronym
            for phrase in potential_skills:
                # Basic heuristic: if it has uppercase inside (e.g. FastAPI, TensorFlow) or numbers (e.g. GPT4)
                if re.search(r'[A-Z].*[A-Z]', phrase) or re.search(r'\d', phrase):
                    canonical, conf = self.canonicalize(phrase)
                    if conf > 0.8:
                        extracted_canonical.add(canonical)
                    else:
                        extracted_canonical.add(phrase.title())
                
        return list(extracted_canonical)
