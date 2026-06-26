"""
Resume embedder — generates multi-vector section embeddings.

Creates separate embeddings for: summary, experience, projects,
skills, education. All L2-normalized float32.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from src.jd.jd_embedder import embed_texts_batch
from src.utils.logger import get_logger

logger = get_logger("resume_embedder")


def embed_resume(
    parsed_resume: dict,
    model_name: str = "BAAI/bge-base-en-v1.5",
    save_dir: Optional[str] = None,
) -> dict[str, np.ndarray]:
    """
    Generate multi-vector embeddings for a parsed resume.

    Embeds 5 sections:
    - summary: Summary/objective text
    - experience: Concatenated experience bullets
    - projects: Concatenated project descriptions
    - skills: Skills list as a sentence
    - education: Education text

    Args:
        parsed_resume: Dict with sections, experience, projects, skills, education.
        model_name: Sentence transformer model name.
        save_dir: Optional directory to save .npy files.

    Returns:
        Dict of embedding arrays keyed by section name.
    """
    sections = parsed_resume.get("sections", {})
    experience = parsed_resume.get("experience", [])
    projects = parsed_resume.get("projects", [])
    skills = parsed_resume.get("skills", [])
    education = parsed_resume.get("education", [])

    texts_to_embed: dict[str, str] = {}

    # Summary
    summary = sections.get("summary", "") or sections.get("header", "")
    if summary:
        texts_to_embed["summary"] = summary

    # Experience — concatenate all bullets
    exp_texts = []
    for exp in experience:
        bullets = exp.get("bullets", [])
        if bullets:
            exp_texts.extend(bullets)
        role = exp.get("role", "")
        company = exp.get("company", "")
        if role or company:
            exp_texts.append(f"{role} at {company}")
    if exp_texts:
        texts_to_embed["experience"] = " ".join(exp_texts)

    # Projects — concatenate descriptions
    proj_texts = []
    for proj in projects:
        desc = proj.get("description", "")
        title = proj.get("title", "")
        techs = proj.get("technologies", [])
        if desc:
            proj_texts.append(f"{title}: {desc}")
        elif title:
            proj_texts.append(f"{title} using {', '.join(techs)}" if techs else title)
    if proj_texts:
        texts_to_embed["projects"] = " ".join(proj_texts)

    # Skills — as a comma-separated sentence
    if skills:
        texts_to_embed["skills"] = ", ".join(skills)

    # Education
    edu_texts = []
    for edu in education:
        inst = edu.get("institution", "")
        degree = edu.get("degree", "")
        major = edu.get("major", "")
        if any([inst, degree, major]):
            edu_texts.append(f"{degree} in {major} from {inst}".strip())
    if edu_texts:
        texts_to_embed["education"] = " ".join(edu_texts)

    # Batch embed all sections
    if not texts_to_embed:
        logger.warning("No text sections to embed for resume")
        return {}

    keys = list(texts_to_embed.keys())
    texts = [texts_to_embed[k] for k in keys]

    all_embeddings = embed_texts_batch(texts, model_name=model_name)

    embeddings: dict[str, np.ndarray] = {}
    for i, key in enumerate(keys):
        embeddings[key] = all_embeddings[i]

    # Also create a weighted composite embedding
    weights = {
        "summary": 0.15,
        "experience": 0.35,
        "projects": 0.20,
        "skills": 0.20,
        "education": 0.10,
    }

    composite = np.zeros_like(next(iter(embeddings.values())))
    total_weight = 0.0
    for key, emb in embeddings.items():
        w = weights.get(key, 0.1)
        composite += w * emb
        total_weight += w

    if total_weight > 0:
        composite /= total_weight
        # L2-normalize
        norm = np.linalg.norm(composite)
        if norm > 0:
            composite /= norm
        embeddings["composite"] = composite.astype(np.float32)

    # Save if directory provided
    if save_dir:
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        candidate_id = parsed_resume.get("candidate_id", "unknown")
        for key, emb in embeddings.items():
            np.save(str(save_path / f"{candidate_id}_{key}.npy"), emb)
        logger.debug(f"Saved {len(embeddings)} embeddings to {save_dir}")

    return embeddings
