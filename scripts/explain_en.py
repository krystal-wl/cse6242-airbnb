"""Elastic net contributions for each September listing.

Run after score_listings.py:  python scripts/explain_en.py jersey-city  (or --all)
Writes data/results/en_contributions/<city>_<snapshot>.csv
"""

import argparse
from copy import copy

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from score_listings import ROOT, SNAPSHOTS, strfair


def feature_of_column(pre):
    """Original feature name of every column after preprocessing (one-hot levels keep their feature's name)."""
    numeric = list(pre.named_transformers_["num"].get_feature_names_out())
    onehot = copy(pre.named_transformers_["cat"]).set_params(feature_name_combiner=lambda feature, level: feature)
    return np.array(numeric + list(onehot.get_feature_names_out()))


def waterfall(base, log_steps):
    """Dollar value of each log step, adding the biggest step first (the order the card shows).

    A log step multiplies the price, so its dollar value depends on the price before it.
    Fixing the order gives each step one value, and the steps add up to the final price.
    """
    dollars = np.zeros_like(log_steps)
    for i in range(len(base)):
        price = base[i]
        for j in np.argsort(-np.abs(log_steps[i])):
            new_price = price * np.exp(log_steps[i, j])
            dollars[i, j] = new_price - price
            price = new_price
    return dollars


def explain_fold(X_train, y_train, X_test):
    # Same model and same training rows as score_listings.py, so the prices match.
    model = strfair.make_elastic_net(X_train)
    model.fit(X_train, y_train)
    pre, en = model.steps[0][1], model.steps[1][1]

    # The model is linear in log price: prediction = start + sum(coef * value).
    # Start from the average training listing; each feature adds coef * (value - average).
    mean = np.asarray(pre.transform(X_train).mean(axis=0)).ravel()
    start = en.intercept_ + mean @ en.coef_
    encoded = pre.transform(X_test)
    names = feature_of_column(pre)

    contributions = pd.DataFrame(index=X_test.index)
    for feature in X_train.columns:
        cols = names == feature  # a one-hot feature has several columns
        contributions[feature] = encoded[:, cols] @ en.coef_[cols] - mean[cols] @ en.coef_[cols]

    result = pd.DataFrame({"en_reference_price": np.exp(start + contributions.sum(axis=1))})
    return result.join(contributions.add_prefix("feature_log_"))


def from_stay_type_base(rows, monthly, groups):
    """Measure contributions from the typical listing of the same stay type, in dollars by group."""
    # Monthly quotes are about half the nightly level, so each stay type gets its own base:
    # the geometric mean of the EN fair prices of that stay type.
    log_fair = np.log(rows["en_reference_price"])
    base_log = log_fair.groupby(monthly).transform("mean")
    feature_log = rows.filter(like="feature_log_")
    feature_log = feature_log - feature_log.groupby(monthly).transform("mean")

    # Each fold model has a slightly different starting point. That gap is not a feature,
    # so it is kept apart as the last step (at most ~3% of the price).
    offset = log_fair - base_log - feature_log.sum(axis=1)

    names = [c.removeprefix("feature_log_") for c in feature_log.columns]
    feature_groups = groups.reindex(names)
    if feature_groups.isna().any():
        raise ValueError(f"no group in decisions.csv for {list(feature_groups[feature_groups.isna()].index)}")
    by_group = feature_log.T.groupby(feature_groups.to_numpy()).sum().T

    out = pd.DataFrame(index=rows.index)
    out["stay_type"] = np.where(monthly == 1, "monthly", "nightly")
    out["base_price"] = np.exp(base_log)
    dollars = waterfall(out["base_price"].to_numpy(), by_group.to_numpy())
    for i, group in enumerate(by_group.columns):
        out[f"waterfall_{group}"] = dollars[:, i]
    price_after_groups = np.exp(base_log + by_group.sum(axis=1))
    out["waterfall_fold_offset"] = price_after_groups * np.expm1(offset)
    out["en_reference_price"] = rows["en_reference_price"]
    return out.join(feature_log)


def explain_city(city, groups):
    snapshot = SNAPSHOTS[city]
    data = strfair.prepare(city, snapshot)
    features = data.features.set_index("id")
    X = strfair.feature_matrix(features, strfair.ENET_FEATURES)
    hosts = data.sample.set_index("id").loc[X.index, "host_id"]

    results = strfair.DATA_DIR / "results"
    filename = f"{city}_{snapshot}.csv"
    scores = pd.read_csv(results / "scores" / filename).set_index("listing_id")

    # Same host-grouped folds as score_listings.py (GroupKFold has no randomness).
    parts = []
    for fold, (train, test) in enumerate(GroupKFold(n_splits=5).split(X, groups=hosts), start=1):
        part = explain_fold(X.iloc[train], features["log_price"].iloc[train], X.iloc[test])
        part.insert(0, "fold", fold)
        parts.append(part)
    rows = pd.concat(parts).loc[scores.index]

    # The refitted models must give the same prices as score_listings.py.
    expected = scores["en_reference_price"]
    np.testing.assert_allclose(rows["en_reference_price"], expected, rtol=1e-8)

    out = from_stay_type_base(rows, features.loc[rows.index, "is_monthly_quote"], groups)
    out.insert(0, "fold", rows["fold"])

    # base_price plus every step must land on the fair price.
    end = out["base_price"] + out.filter(like="waterfall_").sum(axis=1)
    np.testing.assert_allclose(end, expected, rtol=1e-8)

    out.insert(0, "snapshot", snapshot)
    out.insert(0, "city", city)
    (results / "en_contributions").mkdir(parents=True, exist_ok=True)
    out.to_csv(results / "en_contributions" / filename, index_label="listing_id")
    print(f"{city}: {len(out):,} listings explained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city", nargs="?", choices=SNAPSHOTS)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    cities = list(SNAPSHOTS) if args.all else [args.city]
    if cities == [None]:
        parser.error("give a city or --all")

    decisions = pd.read_csv(ROOT / "docs/eda/feature_lists/decisions.csv")
    groups = decisions.set_index("column")["group"]
    for city in cities:
        explain_city(city, groups)
