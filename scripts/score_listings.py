"""Out-of-fold fair prices from both models for each listing.

Run:  python scripts/score_listings.py jersey-city  (or --all; add --release june for June)
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

# September is what the map shows. June is the previous release, for the stability check.
RELEASES = {
    "september": {
        "jersey-city": "2026-09-21",
        "clark-county-nv": "2026-09-20",
        "los-angeles": "2026-09-14",
        "new-york-city": "2026-09-14",
        "san-diego": "2026-09-20",
        "toronto": "2026-09-16",
    },
    "june": dict(strfair.PINNED_SNAPSHOTS),
}


def cities_to_run():
    """(city, snapshot) pairs from the command line, shared by the three scripts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("city", nargs="?", choices=RELEASES["september"])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--release", choices=RELEASES, default="september")
    args = parser.parse_args()
    if not args.all and args.city is None:
        parser.error("give a city or --all")
    snapshots = RELEASES[args.release]
    cities = list(snapshots) if args.all else [args.city]
    return [(city, snapshots[city]) for city in cities]


def oof_prices(X, y, folds, make_model):
    """Each listing's price comes from a model trained on the other four folds."""
    log_prices = np.full(len(X), np.nan)
    for train, test in folds:
        model = make_model(X.iloc[train])  # settings tuned on June, fitted on the snapshot being scored
        model.fit(X.iloc[train], y.iloc[train])
        log_prices[test] = model.predict(X.iloc[test])
    assert np.isfinite(log_prices).all(), "some listings got no prediction"
    return np.exp(log_prices)


def score_city(city, snapshot):
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
    runs = cities_to_run()
    folder = strfair.DATA_DIR / "results" / "scores"
    folder.mkdir(parents=True, exist_ok=True)
    for city, snapshot in runs:
        scores = score_city(city, snapshot)
        scores.to_csv(folder / f"{city}_{snapshot}.csv", index=False)
        print(f"{city}: {len(scores):,} listings scored")
