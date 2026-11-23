"""Out-of-fold fair prices from both models for each September listing.

Run:  python scripts/score_listings.py jersey-city  (or --all)
Writes data/results/scores/<city>_<snapshot>.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strfair  # noqa: E402

SNAPSHOTS = {
    "jersey-city": "2026-09-21",
    "clark-county-nv": "2026-09-20",
    "los-angeles": "2026-09-14",
    "new-york-city": "2026-09-14",
    "san-diego": "2026-09-20",
    "toronto": "2026-09-16",
}


def oof_prices(X, y, folds, make_model):
    """Each listing's price comes from a model trained on the other four folds."""
    log_prices = np.full(len(X), np.nan)
    for train, test in folds:
        model = make_model(X.iloc[train])  # settings tuned on June, fitted on September
        model.fit(X.iloc[train], y.iloc[train])
        log_prices[test] = model.predict(X.iloc[test])
    assert np.isfinite(log_prices).all(), "some listings got no prediction"
    return np.exp(log_prices)


def score_city(city):
    snapshot = SNAPSHOTS[city]
    data = strfair.prepare(city, snapshot)
    features = data.features
    y = features["log_price"]

    # Folds by host: a host's near-identical listings are never split between training and test.
    folds = list(GroupKFold(n_splits=5).split(features, groups=data.sample["host_id"]))
    X_en = strfair.feature_matrix(features, strfair.ENET_FEATURES)
    X_rf = strfair.feature_matrix(features, strfair.RF_FEATURES)

    return pd.DataFrame({
        "listing_id": features["id"],
        "city": city,
        "snapshot": snapshot,
        "actual_price": features["price"],
        "en_reference_price": oof_prices(X_en, y, folds, strfair.make_elastic_net),
        "rf_reference_price": oof_prices(X_rf, y, folds, strfair.make_random_forest),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city", nargs="?", choices=SNAPSHOTS)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    cities = list(SNAPSHOTS) if args.all else [args.city]
    if cities == [None]:
        parser.error("give a city or --all")

    folder = strfair.DATA_DIR / "results" / "scores"
    folder.mkdir(parents=True, exist_ok=True)
    for city in cities:
        scores = score_city(city)
        scores.to_csv(folder / f"{city}_{SNAPSHOTS[city]}.csv", index=False)
        print(f"{city}: {len(scores):,} listings scored")
