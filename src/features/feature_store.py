"""
Parquet-based feature store for candidate feature vectors.

Provides read/write operations for the pre-computed feature store.
Features are stored as Parquet files indexed by candidate_id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger("feature_store")


class FeatureStore:
    """
    Parquet-based feature store for candidate feature vectors.

    Stores features as columnar Parquet files for efficient retrieval
    with column pruning (only load selected features).
    """

    def __init__(self, base_dir: str = "./data/features") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_parquet_path(self, feature_version: str = "v1") -> Path:
        """Get the Parquet file path for a feature version."""
        return self.base_dir / f"features_{feature_version}.parquet"

    def write_features(
        self,
        candidate_id: str,
        features: dict[str, float],
        feature_version: str = "v1",
    ) -> str:
        """
        Write features for a single candidate.

        Appends to existing Parquet file or creates a new one.

        Args:
            candidate_id: Candidate UUID.
            features: Dict of feature_name → value.
            feature_version: Feature configuration version.

        Returns:
            Path to the Parquet file.
        """
        parquet_path = self._get_parquet_path(feature_version)

        # Create DataFrame for new row
        row_data = {"candidate_id": candidate_id, **features}
        new_df = pd.DataFrame([row_data])

        if parquet_path.exists():
            # Read existing and append
            existing_df = pd.read_parquet(parquet_path)
            # Remove existing row for this candidate (if re-computing)
            existing_df = existing_df[existing_df["candidate_id"] != candidate_id]
            df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            df = new_df

        df.to_parquet(parquet_path, engine="pyarrow", compression="snappy")
        logger.debug(f"Wrote features for {candidate_id} to {parquet_path}")

        return str(parquet_path)

    def write_features_batch(
        self,
        candidates_features: list[dict],
        feature_version: str = "v1",
    ) -> str:
        """
        Write features for multiple candidates at once.

        Args:
            candidates_features: List of dicts with "candidate_id" + feature values.
            feature_version: Feature configuration version.

        Returns:
            Path to the Parquet file.
        """
        parquet_path = self._get_parquet_path(feature_version)

        df = pd.DataFrame(candidates_features)
        df.to_parquet(parquet_path, engine="pyarrow", compression="snappy")
        logger.info(f"Wrote {len(df)} feature vectors to {parquet_path}")

        return str(parquet_path)

    def read_features(
        self,
        candidate_ids: list[str],
        feature_names: Optional[list[str]] = None,
        feature_version: str = "v1",
    ) -> pd.DataFrame:
        """
        Read features for specific candidates.

        Uses column pruning to only load requested features.

        Args:
            candidate_ids: List of candidate IDs to retrieve.
            feature_names: Optional list of specific features to load.
            feature_version: Feature configuration version.

        Returns:
            DataFrame with candidate_id and requested features.
        """
        parquet_path = self._get_parquet_path(feature_version)

        if not parquet_path.exists():
            logger.warning(f"Feature store not found: {parquet_path}")
            return pd.DataFrame()

        # Column pruning: only load needed columns
        columns = ["candidate_id"]
        if feature_names:
            columns.extend(feature_names)

        df = pd.read_parquet(parquet_path, columns=columns if feature_names else None)

        # Filter to requested candidates
        df = df[df["candidate_id"].isin(candidate_ids)]

        logger.debug(
            f"Read features for {len(df)}/{len(candidate_ids)} candidates "
            f"({len(df.columns)} columns)"
        )
        return df

    def read_all_features(
        self,
        feature_version: str = "v1",
    ) -> pd.DataFrame:
        """Read all features from the store."""
        parquet_path = self._get_parquet_path(feature_version)
        if not parquet_path.exists():
            return pd.DataFrame()
        return pd.read_parquet(parquet_path)

    def get_feature_matrix(
        self,
        candidate_ids: list[str],
        feature_names: list[str],
        feature_version: str = "v1",
    ) -> tuple[np.ndarray, list[str]]:
        """
        Get a numpy feature matrix for ranking.

        Args:
            candidate_ids: Ordered list of candidate IDs.
            feature_names: Ordered list of feature names.
            feature_version: Feature version.

        Returns:
            Tuple of (feature_matrix, matched_candidate_ids).
        """
        df = self.read_features(candidate_ids, feature_names, feature_version)

        if df.empty:
            return np.zeros((0, len(feature_names))), []

        # Ensure correct order
        df = df.set_index("candidate_id").reindex(candidate_ids)
        matched = [cid for cid in candidate_ids if cid in df.index and not df.loc[cid].isna().all()]

        if not matched:
            return np.zeros((0, len(feature_names))), []

        df = df.loc[matched]

        # Fill missing features with 0
        for col in feature_names:
            if col not in df.columns:
                df[col] = 0.0

        matrix = df[feature_names].fillna(0).values.astype(np.float32)

        return matrix, matched
