"""Randomized-search Random forest hyperparams on 05's RF_FEATURES.

Loads cached parquet data from `_cache_dir(city, snapshot)` without checking
`code_hash`, and uses GroupKFold(5) by host on the team's pinned snapshots.
Samples one shared set of `n_iter` hyperparameter combinations and evaluates
every combination across all selected cities so mean MAE can be averaged cleanly.
Default: all six cities (mean MAE across cities). Pass a subset to restrict.
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import randint
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.model_selection import GroupKFold, ParameterSampler, cross_val_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strfair.config import PINNED_SNAPSHOTS
from strfair.models import RF_FEATURES, RF_PARAMS, feature_matrix, make_random_forest
from strfair.prep import CityData, _cache_dir, _read_parquet

# Train/tune on pinned snapshots
SNAPSHOTS = dict(PINNED_SNAPSHOTS)

N_ITER = 20  # number of shared random hyperparameter combinations to evaluate
N_SPLITS = 5
SEED = 42

PARAM_DISTRIBUTIONS = {
    "n_estimators": randint(100, 501),      # 100 to 500 trees
    "min_samples_leaf": randint(2, 16),     # 2 to 15 samples per leaf
    "max_features": ["sqrt", "log2", 0.5, None],
    "max_depth": randint(10, 31),
    "min_samples_split": randint(4, 31),
}


class StrfairRFWrapper(BaseEstimator, RegressorMixin):
    """Wraps strfair.models.make_random_forest for scikit-learn CV utilities."""

    def __init__(
        self,
        n_estimators: int = 100,
        min_samples_leaf: int = 5,
        max_features=None,
        max_depth=None,
        min_samples_split: int = 2,
        random_state: int = SEED,
    ):
        self.n_estimators = n_estimators
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.random_state = random_state

    def fit(self, X, y):
        kwargs = {
            "n_estimators": int(self.n_estimators),
            "min_samples_leaf": int(self.min_samples_leaf),
            "max_features": self.max_features,
            "random_state": self.random_state,
        }
        sig = inspect.signature(make_random_forest).parameters
        if "max_depth" in sig:
            kwargs["max_depth"] = None if self.max_depth is None else int(self.max_depth)
        if "min_samples_split" in sig:
            kwargs["min_samples_split"] = int(self.min_samples_split)

        self.estimator_ = make_random_forest(X, **kwargs)
        if ("max_depth" not in sig or "min_samples_split" not in sig) and hasattr(
            self.estimator_, "set_params"
        ):
            rf_params = {}
            if "max_depth" not in sig:
                rf_params["randomforestregressor__max_depth"] = (
                    None if self.max_depth is None else int(self.max_depth)
                )
            if "min_samples_split" not in sig:
                rf_params["randomforestregressor__min_samples_split"] = int(
                    self.min_samples_split
                )
            try:
                self.estimator_.set_params(**rf_params)
            except ValueError:
                pass

        self.estimator_.fit(X, y)
        return self

    def predict(self, X):
        return self.estimator_.predict(X)


def load_cached_city_data(city: str, snapshot: str) -> CityData:
    folder = _cache_dir(city, snapshot)
    listings_path = folder / "listings.parquet"
    features_path = folder / "features.parquet"
    if not listings_path.exists() or not features_path.exists():
        raise FileNotFoundError(
            f"Cached parquet files not found for {city}@{snapshot} in {folder}"
        )
    listings = _read_parquet(listings_path)
    features = _read_parquet(features_path)
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return CityData(city, snapshot, listings, features, meta)


def load_city(city: str, snapshot: str):
    data = load_cached_city_data(city, snapshot)
    X = feature_matrix(data.features, RF_FEATURES)
    y = data.features["log_price"]
    groups = data.sample["host_id"].values
    return X, y, groups


def sample_param_candidates(
    param_distributions: dict, n_iter: int, seed: int
) -> list[dict]:
    """Draw n_iter shared hyperparameter combinations once across all cities."""
    return list(ParameterSampler(param_distributions, n_iter=n_iter, random_state=seed))


def cv_mae_for_params(X, y, groups, params: dict) -> float:
    """5-fold GroupKFold MAE on log_price for a single sampled parameter dict."""
    gkf = GroupKFold(n_splits=N_SPLITS)
    estimator = StrfairRFWrapper(random_state=SEED, **params)
    scores = cross_val_score(
        estimator,
        X,
        y,
        groups=groups,
        cv=gkf,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
    )
    return float(-np.mean(scores))


def main(cities: list[str], n_iter: int) -> None:
    print("baseline RF_PARAMS:", RF_PARAMS)
    print("param distributions:", {k: str(v) for k, v in PARAM_DISTRIBUTIONS.items()})
    print("cities:", cities)
    print(f"n_iter: {n_iter} (= {n_iter * N_SPLITS} RF fits per city)")

    city_data = []
    for city in cities:
        snap = SNAPSHOTS[city]
        print(f"\nloading cached {city}@{snap} from {_cache_dir(city, snap)} ...", flush=True)
        X, y, groups = load_city(city, snap)
        print(f"  n={len(y):,}  features={X.shape[1]}", flush=True)
        city_data.append((city, X, y, groups))

    candidates = sample_param_candidates(PARAM_DISTRIBUTIONS, n_iter=n_iter, seed=SEED)
    print(
        f"\nevaluating {len(candidates)} shared random parameter sets across {len(cities)} cities...\n",
        flush=True,
    )

    group_cols = [
        "candidate_id",
        "n_estimators",
        "max_depth",
        "min_samples_split",
        "min_samples_leaf",
        "max_features",
    ]

    rows = []
    for idx, params in enumerate(candidates, start=1):
        n_est = int(params["n_estimators"])
        max_depth = None if params.get("max_depth") is None else int(params["max_depth"])
        min_split = int(params["min_samples_split"])
        leaf = int(params["min_samples_leaf"])
        max_feat = params["max_features"]

        city_maes = []
        for city, X, y, groups in city_data:
            mae = cv_mae_for_params(X, y, groups, params)
            city_maes.append(mae)
            rows.append({
                "candidate_id": idx,
                "n_estimators": n_est,
                "max_depth": max_depth if max_depth is not None else "None",
                "min_samples_split": min_split,
                "min_samples_leaf": leaf,
                "max_features": max_feat if max_feat is not None else "None",
                "city": city,
                "mae_log": mae,
            })

        mean_mae = float(np.mean(city_maes))
        print(
            f"[{idx:>2}/{len(candidates)}] n_est={n_est:<4} depth={str(max_depth):<4} "
            f"split={min_split:<2} leaf={leaf:<2} max_feat={str(max_feat):<5}  "
            f"mean MAE(log)={mean_mae:.4f}  per city={np.round(city_maes, 4)}",
            flush=True,
        )

    result = pd.DataFrame(rows)
    summary = (
        result.groupby(group_cols, as_index=False)["mae_log"]
        .mean()
        .rename(columns={"mae_log": "mean_mae_log"})
        .sort_values("mean_mae_log")
    )
    print("\n=== top 5 by mean MAE(log) ===")
    print(summary.head(5).to_string(index=False))

    best = summary.iloc[0]
    best_max_feat = None if best["max_features"] == "None" else best["max_features"]
    best_max_depth = None if best["max_depth"] == "None" else int(best["max_depth"])
    print("\nBest params to consider for strfair/models.py RF_PARAMS:")
    print(
        f"  n_estimators={int(best['n_estimators'])}, "
        f"max_depth={best_max_depth!r}, "
        f"min_samples_split={int(best['min_samples_split'])}, "
        f"min_samples_leaf={int(best['min_samples_leaf'])}, "
        f"max_features={best_max_feat!r}  (mean MAE={best['mean_mae_log']:.4f})"
    )

    out = ROOT / "docs" / "eda" / "rf_tuning_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "cities",
        nargs="*",
        default=list(SNAPSHOTS),
        help="cities to include (default: all six)",
    )
    p.add_argument(
        "--n-iter",
        type=int,
        default=N_ITER,
        help=f"number of shared random parameter combinations (default: {N_ITER})",
    )
    args = p.parse_args()
    unknown = [c for c in args.cities if c not in SNAPSHOTS]
    if unknown:
        sys.exit(f"unknown cities: {unknown}; choose from {list(SNAPSHOTS)}")
    main(args.cities, args.n_iter)