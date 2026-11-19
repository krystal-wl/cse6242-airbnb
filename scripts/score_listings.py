"""Export September 2026 host-grouped out-of-fold prices in local currency.

Run from the repository root:
    python scripts/score_listings.py jersey-city
    python scripts/score_listings.py --all
"""

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strfair

# Pin each city to its September release so repeated runs use the same data.
SNAPSHOTS = {
    "jersey-city": "2026-09-21",
    "clark-county-nv": "2026-09-20",
    "los-angeles": "2026-09-14",
    "new-york-city": "2026-09-14",
    "san-diego": "2026-09-20",
    "toronto": "2026-09-16",
}


def predict_prices(X, y, folds, make_model):
    """Fit on four folds and predict prices for the hosts in the fifth."""
    # Reserve one slot per listing. A missed prediction stays NaN and fails the check below.
    prices = np.full(len(X), np.nan)
    for train, test in folds:
        X_train, X_test = X.iloc[train], X.iloc[test]
        y_train = y.iloc[train]

        # Start a fresh pipeline with the June-tuned settings. Fit it on these September training rows.
        model = make_model(X_train)
        model.fit(X_train, y_train)
        # Undo the log transform and write each prediction back to its original row position.
        prices[test] = np.exp(model.predict(X_test))

    if not np.all(np.isfinite(prices) & (prices > 0)):
        raise ValueError("Every listing needs a positive, finite predicted price")
    return prices


def score_city(city: str) -> pd.DataFrame:
    # 1. Load the September snapshot and match hosts to listings by ID.
    snapshot = SNAPSHOTS[city]
    data = strfair.prepare(city, snapshot)
    features = data.features.set_index("id", drop=False)
    sample = data.sample.set_index("id")
    if not features.index.is_unique or not sample.index.is_unique:
        raise ValueError(f"{city}: duplicate listing IDs")
    if not features.index.sort_values().equals(sample.index.sort_values()):
        raise ValueError(f"{city}: sample and feature listing IDs differ")

    # Look up hosts in feature-row order so each fold assignment follows the correct listing.
    hosts = sample.loc[features.index, "host_id"]
    if hosts.isna().any():
        raise ValueError(f"{city}: missing host IDs prevent host-grouped scoring")

    # 2. Use the same five host-grouped folds for both tuned models.
    # All listings from one host stay together, so a held-out host is unseen during fitting.
    folds = list(GroupKFold(n_splits=5).split(features, groups=hosts))
    y = features["log_price"]
    # Elastic Net and Random Forest each use the feature list selected for that model.
    X_en = strfair.feature_matrix(features, strfair.ENET_FEATURES)
    X_rf = strfair.feature_matrix(features, strfair.RF_FEATURES)

    # 3. Collect both out-of-fold prices in the same listing order.
    # Keep both reference prices so the team can choose a model and label threshold later.
    return pd.DataFrame({
        "listing_id": features.index,
        "city": city,
        "snapshot": snapshot,
        "actual_price": features["price"].to_numpy(),
        "en_reference_price": predict_prices(X_en, y, folds, strfair.make_elastic_net),
        "rf_reference_price": predict_prices(X_rf, y, folds, strfair.make_random_forest),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cities", nargs="*", metavar="CITY", help=", ".join(SNAPSHOTS))
    parser.add_argument("--all", action="store_true", help="score all six cities")
    args = parser.parse_args()
    if not args.all and not args.cities:
        parser.error("provide one or more cities, or --all")
    if args.all and args.cities:
        parser.error("use either city names or --all")
    cities = list(SNAPSHOTS) if args.all else list(dict.fromkeys(args.cities))
    for city in cities:
        if city not in SNAPSHOTS:
            parser.error(f"unknown city {city!r}; choose from {', '.join(SNAPSHOTS)}")

    folder = strfair.DATA_DIR / "results" / "scores"
    folder.mkdir(parents=True, exist_ok=True)
    for city in cities:
        scores = score_city(city)
        path = folder / f"{city}_{SNAPSHOTS[city]}.csv"
        # Only replace the previous CSV once the new file has finished writing.
        with TemporaryDirectory(dir=folder) as temp_dir:
            temp_path = Path(temp_dir) / path.name
            scores.to_csv(temp_path, index=False)
            temp_path.replace(path)
        print(f"Wrote {len(scores):,} listings to {path}", flush=True)


if __name__ == "__main__":
    main()
