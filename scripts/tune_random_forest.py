"""Grid-search Random forest hyperparams on 05's RF_FEATURES.

Uses GroupKFold(5) by host on the team's **June** snapshots (PINNED_SNAPSHOTS).
Default: all six cities (mean MAE across cities). Pass a subset to restrict.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strfair
from strfair.config import PINNED_SNAPSHOTS
from strfair.models import RF_FEATURES, RF_PARAMS, feature_matrix, make_random_forest

# Train/tune on June
SNAPSHOTS = dict(PINNED_SNAPSHOTS)

# Keep the grid modest: each combo × 5 folds × RF is slow.
N_ESTIMATORS = [100, 300, 500]
MIN_SAMPLES_LEAF = [2, 5, 10]
MAX_FEATURES = ["sqrt", None]  # None = all features at each split
N_SPLITS = 5
SEED = 42


def load_city(city: str, snapshot: str):
    warnings.filterwarnings("ignore", message=".*not a team snapshot.*")
    data = strfair.prepare(city, snapshot)
    X = feature_matrix(data.features, RF_FEATURES)
    y = data.features["log_price"]
    groups = data.sample["host_id"].values
    return X, y, groups


def cv_mae(X, y, groups, n_estimators: int, min_samples_leaf: int, max_features) -> float:
    gkf = GroupKFold(n_splits=N_SPLITS)
    maes = []
    for train_idx, test_idx in gkf.split(X, y, groups):
        model = make_random_forest(
            X,
            n_estimators=n_estimators,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=SEED,
        )
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[test_idx])
        maes.append(mean_absolute_error(y.iloc[test_idx], pred))
    return float(np.mean(maes))


def main(cities: list[str]) -> None:
    print("baseline RF_PARAMS:", RF_PARAMS)
    print("grid n_estimators", N_ESTIMATORS)
    print("grid min_samples_leaf", MIN_SAMPLES_LEAF)
    print("grid max_features", MAX_FEATURES)
    print("cities:", cities)
    n_combos = len(N_ESTIMATORS) * len(MIN_SAMPLES_LEAF) * len(MAX_FEATURES)
    print(f"combos: {n_combos} (= {n_combos * N_SPLITS} RF fits per city)")

    city_data = []
    for city in cities:
        snap = SNAPSHOTS[city]
        print(f"\nloading {city}@{snap} ...", flush=True)
        X, y, groups = load_city(city, snap)
        print(f"  n={len(y):,}  features={X.shape[1]}", flush=True)
        city_data.append((city, X, y, groups))

    rows = []
    for n_est in N_ESTIMATORS:
        for leaf in MIN_SAMPLES_LEAF:
            for max_feat in MAX_FEATURES:
                city_maes = []
                for city, X, y, groups in city_data:
                    mae = cv_mae(X, y, groups, n_est, leaf, max_feat)
                    city_maes.append(mae)
                    rows.append({
                        "n_estimators": n_est,
                        "min_samples_leaf": leaf,
                        "max_features": max_feat if max_feat is not None else "None",
                        "city": city,
                        "mae_log": mae,
                    })
                mean_mae = float(np.mean(city_maes))
                print(
                    f"n_estimators={n_est:<4} min_samples_leaf={leaf:<3} "
                    f"max_features={str(max_feat):<5}  mean MAE(log)={mean_mae:.4f}  "
                    f"per city={np.round(city_maes, 4)}",
                    flush=True,
                )

    result = pd.DataFrame(rows)
    summary = (
        result.groupby(["n_estimators", "min_samples_leaf", "max_features"], as_index=False)["mae_log"]
        .mean()
        .rename(columns={"mae_log": "mean_mae_log"})
        .sort_values("mean_mae_log")
    )
    print("\n=== top 5 by mean MAE(log) ===")
    print(summary.head(5).to_string(index=False))

    best = summary.iloc[0]
    max_feat = None if best["max_features"] == "None" else best["max_features"]
    print("\nBest params to put in strfair/models.py RF_PARAMS:")
    print(
        f"  n_estimators={int(best['n_estimators'])}, "
        f"min_samples_leaf={int(best['min_samples_leaf'])}, "
        f"max_features={max_feat!r}  (mean MAE={best['mean_mae_log']:.4f})"
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
    args = p.parse_args()
    unknown = [c for c in args.cities if c not in SNAPSHOTS]
    if unknown:
        sys.exit(f"unknown cities: {unknown}; choose from {list(SNAPSHOTS)}")
    main(args.cities)
