"""Label September listings using the saved EN and RF predictions.

Run from the repository root:
    python scripts/label_listings.py jersey-city
    python scripts/label_listings.py --all
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from score_listings import SNAPSHOTS

DATA = Path(__file__).resolve().parents[1] / "data"


def price_label(price_ratio):
    """Prices at exactly 80% or 120% of the benchmark are fairly priced."""
    return np.select(
        [price_ratio < 0.80, price_ratio > 1.20],
        ["underpriced", "overpriced"],
        default="fairly priced",
    )


def label_city(city):
    snapshot = SNAPSHOTS[city]
    filename = f"{city}_{snapshot}.csv"
    scores = pd.read_csv(DATA / "results" / "scores" / filename)
    if scores.empty or not (scores["city"].eq(city) & scores["snapshot"].eq(snapshot)).all():
        raise ValueError(f"{filename}: expected scores for {city} on {snapshot}")

    # 1. Attach the total review count from the same quarterly release.
    reviews = pd.read_csv(
        DATA / city / snapshot / "listings.csv.gz",
        usecols=["id", "number_of_reviews"],
    ).rename(columns={"id": "listing_id"})
    rows = scores.merge(reviews, on="listing_id", how="left", validate="one_to_one")
    if rows["listing_id"].isna().any() or rows["number_of_reviews"].isna().any():
        raise ValueError(f"{filename}: every scored listing needs an ID and a review count")

    # 2. The EN label drives the map. RF applies the same rule independently.
    prices = rows[["actual_price", "en_reference_price", "rf_reference_price"]]
    if not (np.isfinite(prices) & prices.gt(0)).all().all():
        raise ValueError(f"{filename}: prices must be positive and finite")
    en_ratio = rows["actual_price"] / rows["en_reference_price"]
    rows["en_deviation_pct"] = (en_ratio - 1) * 100
    rows["en_label"] = price_label(en_ratio)
    rows["rf_label"] = price_label(rows["actual_price"] / rows["rf_reference_price"])

    # 3. Keep both reasons so the dashboard can explain the confidence flag.
    rows["model_disagreement"] = rows["en_label"] != rows["rf_label"]
    rows["few_reviews"] = rows["number_of_reviews"] < 3
    rows["low_confidence"] = rows["model_disagreement"] | rows["few_reviews"]

    folder = DATA / "results" / "labels"
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder) as temp_dir:
        temp_path = Path(temp_dir) / filename
        rows.to_csv(temp_path, index=False)
        temp_path.replace(folder / filename)
    print(f"{city}: wrote {len(rows):,} listings to {folder / filename}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cities", nargs="*", metavar="CITY", help=", ".join(SNAPSHOTS))
    parser.add_argument("--all", action="store_true", help="label all six cities")
    args = parser.parse_args()
    if args.all and args.cities:
        parser.error("use either city names or --all")
    if not args.all and not args.cities:
        parser.error("provide one or more cities, or --all")
    cities = SNAPSHOTS if args.all else dict.fromkeys(args.cities)
    for city in cities:
        if city not in SNAPSHOTS:
            parser.error(f"unknown city {city!r}; choose from {', '.join(SNAPSHOTS)}")
    for city in cities:
        label_city(city)


if __name__ == "__main__":
    main()
