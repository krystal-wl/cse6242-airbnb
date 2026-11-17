"""Grid-search Elastic net hyperparams on 05's ENET_FEATURES.

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
from strfair.models import ENET_FEATURES, ENET_PARAMS, feature_matrix, make_elastic_net

# Train/tune on June; Sept holdout is separate.
SNAPSHOTS = dict(PINNED_SNAPSHOTS)

ALPHAS = [0.0001, 0.001, 0.01, 0.05, 0.1]
L1_RATIOS = [0.15, 0.5, 0.85, 1.0]
N_SPLITS = 5
SEED = 42


def load_city(city: str, snapshot: str):
    warnings.filterwarnings("ignore", message=".*not a team snapshot.*")
    data = strfair.prepare(city, snapshot)
    X = feature_matrix(data.features, ENET_FEATURES)
    y = data.features["log_price"]
    groups = data.sample["host_id"].values
    return X, y, groups


def cv_mae(X, y, groups, alpha: float, l1_ratio: float) -> float:
    gkf = GroupKFold(n_splits=N_SPLITS)
    maes = []
    for train_idx, test_idx in gkf.split(X, y, groups):
        model = make_elastic_net(X, alpha=alpha, l1_ratio=l1_ratio)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[test_idx])
        maes.append(mean_absolute_error(y.iloc[test_idx], pred))
    return float(np.mean(maes))


def main(cities: list[str]) -> None:
    print("baseline ENET_PARAMS:", ENET_PARAMS)
    print("grid alphas", ALPHAS, "l1_ratios", L1_RATIOS)
    print("cities:", cities)

    city_data = []
    for city in cities:
        snap = SNAPSHOTS[city]
        print(f"\nloading {city}@{snap} ...")
        X, y, groups = load_city(city, snap)
        print(f"  n={len(y):,}  features={X.shape[1]}")
        city_data.append((city, X, y, groups))

    rows = []
    for alpha in ALPHAS:
        for l1 in L1_RATIOS:
            city_maes = []
            for city, X, y, groups in city_data:
                mae = cv_mae(X, y, groups, alpha, l1)
                city_maes.append(mae)
                rows.append({"alpha": alpha, "l1_ratio": l1, "city": city, "mae_log": mae})
            mean_mae = float(np.mean(city_maes))
            print(f"alpha={alpha:<8} l1_ratio={l1:<4}  mean MAE(log)={mean_mae:.4f}  per city={np.round(city_maes, 4)}")

    result = pd.DataFrame(rows)
    summary = (
        result.groupby(["alpha", "l1_ratio"], as_index=False)["mae_log"]
        .mean()
        .rename(columns={"mae_log": "mean_mae_log"})
        .sort_values("mean_mae_log")
    )
    print("\n=== top 5 by mean MAE(log) ===")
    print(summary.head(5).to_string(index=False))

    best = summary.iloc[0]
    print("\nBest params to put in strfair/models.py ENET_PARAMS:")
    print(f"  alpha={best['alpha']}, l1_ratio={best['l1_ratio']}  (mean MAE={best['mean_mae_log']:.4f})")

    out = ROOT / "docs" / "eda" / "enet_tuning_results.csv"
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
