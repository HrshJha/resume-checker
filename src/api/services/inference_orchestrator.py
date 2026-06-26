"""
End-to-End Inference Orchestrator.

Combines all pipeline phases:
1. Retrieval (Hybrid FAISS + BM25)
2. Reranking (Cross-Encoder)
3. Feature Engineering (Graph, Evidence, Career, Behavior)
4. LTR Ranking (XGBoost)
5. Explainability (SHAP)
6. Fairness Audit
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from src.api.db_models import JobDescription
from src.api.repositories.candidate_repo import CandidateRepository
from src.explainability.shap_explainer import SHAPExplainer, generate_counterfactuals, generate_nl_explanation
from src.features.feature_engineer import FeatureEngineer
from src.ranking.ltr_base import XGBoostRanker
from src.retrieval.cross_encoder_reranker import rerank as cross_encoder_rerank
from src.retrieval.hybrid_retriever import hybrid_search
from src.fairness.fairness_auditor import FairnessAuditor
from src.utils.logger import get_logger

logger = get_logger("inference_orchestrator")


class InferenceOrchestrator:
    """Master orchestrator for candidate ranking."""

    def __init__(
        self,
        candidate_repo: CandidateRepository,
        feature_engineer: FeatureEngineer,
        ranker: XGBoostRanker,
        explainer: SHAPExplainer,
        auditor: FairnessAuditor | None = None,
    ) -> None:
        self.candidate_repo = candidate_repo
        self.feature_engineer = feature_engineer
        self.ranker = ranker
        self.explainer = explainer
        self.auditor = auditor or FairnessAuditor()

    async def rank_candidates(
        self,
        jd: JobDescription,
        top_k: int = 50,
        retrieval_k: int = 500,
        rerank_k: int = 150,
    ) -> dict[str, Any]:
        """
        Execute the full inference pipeline.

        Args:
            jd: The parsed JobDescription model.
            top_k: Final number of candidates to return.
            retrieval_k: Number of candidates to pull from FAISS/BM25.
            rerank_k: Number of candidates to pass to cross-encoder.

        Returns:
            Dict with 'results' (list of candidate dicts) and 'audit' (fairness metrics).
        """
        start_time = time.time()
        logger.info(f"Starting inference pipeline for JD: {jd.jd_id}")

        # In a real system, the jd_embedding would be retrieved from JDRepository
        # Mocking embedding for structural logic demonstration
        mock_jd_embedding = np.random.rand(768)

        # ---------------------------------------------------------
        # PHASE 1: HYBRID RETRIEVAL (FAISS + BM25)
        # ---------------------------------------------------------
        t_start = time.time()
        # Returns: (candidate_id, hybrid_score, dense_score, bm25_score)
        retrieved = hybrid_search(
            query_embedding=mock_jd_embedding,
            query_text=jd.raw_text,  # type: ignore
            top_k=retrieval_k,
            dense_weight=0.7,
        )

        if not retrieved:
            logger.warning("No candidates retrieved from hybrid search.")
            return {"results": [], "processing_time": time.time() - start_time}

        retrieved_ids = [r[0] for r in retrieved]
        retrieval_scores = {
            r[0]: {"hybrid": r[1], "dense": r[2], "bm25": r[3]} for r in retrieved
        }
        logger.debug(f"Phase 1 Retrieval done in {time.time() - t_start:.2f}s")

        # ---------------------------------------------------------
        # PHASE 2: CROSS-ENCODER RERANKING
        # ---------------------------------------------------------
        t_start = time.time()
        # Fetch actual text for top rerank_k candidates
        candidates_to_rerank = retrieved_ids[:rerank_k]
        candidate_models = await self.candidate_repo.get_by_ids(candidates_to_rerank)
        candidate_map = {c.candidate_id: c for c in candidate_models}

        # Prepare text pairs
        rerank_texts = []
        valid_ids = []
        for cid in candidates_to_rerank:
            c = candidate_map.get(cid)  # type: ignore
            if c and c.parsed_data and "full_text" in c.parsed_data:
                rerank_texts.append(c.parsed_data["full_text"])
                valid_ids.append(cid)

        # Rerank
        reranked = cross_encoder_rerank(
            jd_text=jd.raw_text,  # type: ignore
            candidate_texts=rerank_texts,
            candidate_ids=valid_ids,
            top_k=top_k * 2,  # Give LTR a buffer
            batch_size=8,
        )
        logger.debug(f"Phase 2 Reranking done in {time.time() - t_start:.2f}s")

        # ---------------------------------------------------------
        # PHASE 3: FEATURE ENGINEERING
        # ---------------------------------------------------------
        t_start = time.time()
        jd_data = {
            "required_skills": jd.required_skills,
            "seniority": jd.seniority,
        }

        feature_matrix = []
        candidate_meta = []
        [r[0] for r in reranked]

        for cid, ce_score in reranked:
            c = candidate_map[cid]  # type: ignore

            # Combine all retrieval scores
            scores_dict = {
                "dense_score": retrieval_scores[cid]["dense"],
                "bm25_score": retrieval_scores[cid]["bm25"],
                "cross_encoder_score": ce_score,
            }

            c_data = {
                "skills": c.skills or [],
                "experience": c.parsed_data.get("experience", []),
                "projects": c.projects or [],
                "certifications": c.parsed_data.get("certifications", []),
                "full_text": c.parsed_data.get("full_text", ""),
            }

            # Build feature dictionary
            f_dict = self.feature_engineer.build_features(jd_data, c_data, scores_dict)
            feature_matrix.append(self.feature_engineer.vectorize(f_dict))

            # Store metadata for explanation
            candidate_meta.append({
                "candidate_id": cid,
                "features_dict": f_dict,
                "experience_years": c.experience_years,
                "skills": c.skills,
            })

        X = np.array(feature_matrix)
        logger.debug(f"Phase 3 Feature Engineering done in {time.time() - t_start:.2f}s")

        # ---------------------------------------------------------
        # PHASE 4: LTR RANKING (XGBoost)
        # ---------------------------------------------------------
        t_start = time.time()
        try:
            ltr_scores = self.ranker.predict(X)
        except RuntimeError:
            # Model not trained, fallback to cross-encoder scores
            logger.warning("LTR model not trained, falling back to cross-encoder scores")
            ltr_scores = np.array([r[1] for r in reranked])

        # Sort by LTR score descending
        sorted_indices = np.argsort(ltr_scores)[::-1][:top_k]

        final_results = []
        final_X = []
        final_meta = []

        for rank_idx, i in enumerate(sorted_indices, 1):
            meta = candidate_meta[i]
            cid = meta["candidate_id"]
            final_score = float(ltr_scores[i])

            final_results.append({
                "rank": rank_idx,
                "candidate_id": cid,
                "final_score": final_score,
                "semantic_score": float(meta["features_dict"].get("exact_match_ratio", 0.0)),
                "evidence_score": float(meta["features_dict"].get("evidence_score", 0.0)),
                "career_score": float(meta["features_dict"].get("career_score", 0.0)),
                "behavior_score": float(meta["features_dict"].get("behavior_score", 0.0)),
            })
            final_X.append(X[i])
            final_meta.append(meta)

        logger.debug(f"Phase 4 LTR Ranking done in {time.time() - t_start:.2f}s")

        # ---------------------------------------------------------
        # PHASE 5: SHAP EXPLAINABILITY
        # ---------------------------------------------------------
        t_start = time.time()
        if final_X:
            try:
                explanations = self.explainer.explain_batch(np.array(final_X))
                for i, result in enumerate(final_results):
                    contrib = explanations[i]["feature_contributions"]
                    nl_text = generate_nl_explanation(contrib, result["rank"], result["final_score"])
                    cf = generate_counterfactuals(contrib, result["rank"])

                    result["explanation"] = {
                        "shap_values": explanations[i]["shap_values"],
                        "feature_contributions": contrib,
                        "natural_language": nl_text,
                        "counterfactuals": cf,
                    }
            except Exception as e:
                logger.error(f"SHAP explanation failed: {e}")
                for result in final_results:
                    result["explanation"] = {}

        logger.debug(f"Phase 5 Explainability done in {time.time() - t_start:.2f}s")

        # ---------------------------------------------------------
        # PHASE 6: FAIRNESS AUDIT
        # ---------------------------------------------------------
        t_start = time.time()
        audit_results = self.auditor.audit_ranking(
            final_scores=[r["final_score"] for r in final_results],
            features_list=[m["features_dict"] for m in final_meta],
        )
        logger.debug(f"Phase 6 Fairness Audit done in {time.time() - t_start:.2f}s")

        # Total time
        processing_time = time.time() - start_time
        logger.info(f"Inference pipeline completed in {processing_time:.2f}s")

        return {
            "results": final_results,
            "audit": audit_results,
            "processing_time": processing_time,
        }
