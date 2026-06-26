"""
Learning-to-Rank base interface and XGBoost/LightGBM ranker implementations.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("ranking")


class LTRBase(ABC):
    """Abstract base class for Learning-to-Rank models."""

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, **kwargs) -> None:
        """Train the ranker."""

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict relevance scores."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Save model to disk."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load model from disk."""

    @abstractmethod
    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance scores."""


class XGBoostRanker(LTRBase):
    """XGBoost Learning-to-Rank with rank:ndcg objective."""

    def __init__(self, params: Optional[dict] = None) -> None:
        self.params = params or {
            "objective": "rank:ndcg",
            "eval_metric": "ndcg@10",
            "learning_rate": 0.1,
            "max_depth": 6,
            "n_estimators": 500,
            "min_child_weight": 3,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "tree_method": "hist",
            "random_state": 42,
        }
        self.model = None
        self.feature_names: list[str] = []

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        feature_names: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        """Train XGBoost ranker with group information."""
        import xgboost as xgb

        self.feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        # Separate n_estimators from params (it's a fit param)
        params = {k: v for k, v in self.params.items() if k != "n_estimators"}
        n_estimators = self.params.get("n_estimators", 500)

        self.model = xgb.XGBRanker(**params, n_estimators=n_estimators)  # type: ignore
        self.model.fit(  # type: ignore
            X, y,
            group=groups,
            verbose=kwargs.get("verbose", False),
        )

        logger.info(f"XGBoost ranker trained: {n_estimators} estimators, {X.shape[1]} features")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict relevance scores."""
        if self.model is None:
            raise RuntimeError("Model not trained or loaded")
        return self.model.predict(X)

    def save(self, path: str) -> None:
        """Save XGBoost model as JSON."""
        if self.model is None:
            raise RuntimeError("No model to save")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.model.save_model(path)

        # Save feature names alongside
        meta_path = path.replace(".json", "_meta.json")
        with open(meta_path, "w") as f:
            json.dump({"feature_names": self.feature_names}, f)

        logger.info(f"XGBoost model saved to {path}")

    def load(self, path: str) -> None:
        """Load XGBoost model from JSON."""
        import xgboost as xgb

        self.model = xgb.XGBRanker()  # type: ignore
        self.model.load_model(path)  # type: ignore

        meta_path = path.replace(".json", "_meta.json")
        if Path(meta_path).exists():
            with open(meta_path) as f:
                meta = json.load(f)
                self.feature_names = meta.get("feature_names", [])

        logger.info(f"XGBoost model loaded from {path}")

    def get_feature_importance(self) -> dict[str, float]:
        """Get SHAP-based or gain-based feature importance."""
        if self.model is None:
            return {}
        importance = self.model.feature_importances_
        return dict(zip(self.feature_names or [f"f{i}" for i in range(len(importance))], importance.tolist()))


class LightGBMRanker(LTRBase):
    """LightGBM Learning-to-Rank with lambdarank objective."""

    def __init__(self, params: Optional[dict] = None) -> None:
        self.params = params or {
            "objective": "lambdarank",
            "metric": "ndcg",
            "learning_rate": 0.1,
            "num_leaves": 63,
            "min_data_in_leaf": 20,
            "feature_fraction": 0.8,
            "n_estimators": 500,
            "random_state": 42,
        }
        self.model = None
        self.feature_names: list[str] = []

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        feature_names: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        """Train LightGBM ranker with group information."""
        import lightgbm as lgb

        self.feature_names = feature_names or [f"f{i}" for i in range(X.shape[1])]

        self.model = lgb.LGBMRanker(**self.params)  # type: ignore
        self.model.fit(  # type: ignore
            X, y,
            group=groups,
            feature_name=self.feature_names,
            verbose=kwargs.get("verbose", -1),
        )

        logger.info(f"LightGBM ranker trained: {X.shape[1]} features")

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not trained or loaded")
        return self.model.predict(X)

    def save(self, path: str) -> None:
        if self.model is None:
            raise RuntimeError("No model to save")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.model.booster_.save_model(path)

        meta_path = path.replace(".txt", "_meta.json")
        with open(meta_path, "w") as f:
            json.dump({"feature_names": self.feature_names}, f)

        logger.info(f"LightGBM model saved to {path}")

    def load(self, path: str) -> None:
        import lightgbm as lgb

        self.model = lgb.Booster(model_file=path)  # type: ignore

        meta_path = path.replace(".txt", "_meta.json")
        if Path(meta_path).exists():
            with open(meta_path) as f:
                meta = json.load(f)
                self.feature_names = meta.get("feature_names", [])

        logger.info(f"LightGBM model loaded from {path}")

    def get_feature_importance(self) -> dict[str, float]:
        if self.model is None:
            return {}
        if hasattr(self.model, "feature_importances_"):
            importance = self.model.feature_importances_
        elif hasattr(self.model, "feature_importance"):
            importance = self.model.feature_importance(importance_type="gain")
        else:
            return {}
        names = self.feature_names or [f"f{i}" for i in range(len(importance))]
        return dict(zip(names, [float(v) for v in importance]))
