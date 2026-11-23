"""Build the table the map reads from the model outputs (replaces stub_scores.py).

Run after score_listings.py and explain_en.py:  python scripts/build_scored.py jersey-city  (or --all; add --release june)
Writes data/scored/<city>_<snapshot>/scored.parquet and meta.json
"""

import json

import numpy as np
import pandas as pd

from explain_en import waterfall
from score_listings import ROOT, cities_to_run, strfair
from stub_scores import comparables

RESULTS = strfair.DATA_DIR / "results"

# Card groups for the Elastic net features. Finer than decisions.csv: stay length and
# check-in timing are both "target_quote" there, but a reader sees them as different things.
GROUP_OF = {
    "accommodates": "size", "bedrooms": "size", "beds": "size", "baths": "size", "shared_bath": "size",
    "room_type": "room",
    "property_group": "property",
    "neighbourhood": "neighbourhood", "neighbourhood_group": "neighbourhood",
    "latitude": "location", "longitude": "location", "log_km_to_centre": "location",
    "dist_exp_decay": "location", "dist_to_nearest_attraction_km": "location",
    "quote_nights": "stay length", "is_monthly_quote": "stay length", "min_nights_band": "stay length",
    "has_discount": "stay length", "discount_share": "stay length", "maximum_nights": "stay length",
    "lead_days": "check-in", "lead_band": "check-in", "weekend_checkin": "check-in",
    "checkin_dow": "check-in", "checkin_month": "check-in",
    "superhost": "host", "host_listings_count": "host", "log_host_listings": "host",
    "calculated_host_listings_count_entire_homes": "host",
    "calculated_host_listings_count_private_rooms": "host",
    "host_entire_home_share": "host", "host_years": "host", "host_about_len": "host",
    "log_reviews": "reviews", "tenure_months": "reviews", "new_listing": "reviews",
    "months_since_last_review": "reviews",
    "no_rating": "rating", "rating_filled": "rating",
    "sentiment_std": "sentiment", "negative_review_pct": "sentiment", "weighted_sentiment": "sentiment",
    "no_sentiment": "sentiment",
    "n_amenities": "amenities",
    "name_len": "listing text", "desc_len": "listing text",
    "has_license": "licence", "license_exempt": "licence",
}
PREFIX_GROUPS = {"review_scores_": "rating", "amg_": "amenities", "am_": "amenities", "kw_": "listing text"}


def group_of(feature):
    if feature in GROUP_OF:
        return GROUP_OF[feature]
    for prefix, group in PREFIX_GROUPS.items():
        if feature.startswith(prefix):
            return group
    raise KeyError(f"add {feature} to GROUP_OF")  # otherwise it would drop off the card


def count(n, word):
    n = int(round(n))
    return f"{n} {word}" + ("" if n == 1 else "s")


def label(group, row):
    """Card text for one group, with this listing's own values."""
    if group == "size":
        text = "Size: sleeps " + str(int(row["accommodates"]))
        if pd.notna(row["bedrooms"]):
            text += ", " + count(row["bedrooms"], "bedroom")
        if pd.notna(row["baths"]):
            text += f", {row['baths']:g} bath" + ("" if row["baths"] == 1 else "s")
        return text
    if group == "location":
        text = f"{row['km_to_centre']:.1f} km from the centre"
        if pd.notna(row["dist_to_nearest_attraction_km"]):
            text += f", {row['dist_to_nearest_attraction_km']:.1f} km from {row['nearest_attraction']}"
        return text
    if group == "check-in":
        month = pd.to_datetime(row["price_quote_checkin_date"]).strftime("%B")
        return f"Check-in in {month} ({int(row['lead_days'])} days ahead)"
    if group == "host":
        if row["superhost"] == 1:
            return "Host: superhost"
        return "Host with " + count(row["host_listings_count"], "listing") if row["host_listings_count"] > 0 else "Host profile"
    if group == "rating":
        return "No rating yet" if pd.isna(row["review_scores_rating"]) else f"Rating {row['review_scores_rating']:.2f}"
    if group == "licence":
        return "Licence on file" if row["has_license"] == 1 else "Licence exempt" if row["license_exempt"] == 1 else "No licence listed"
    if group == "reviews":
        return count(row["number_of_reviews"], "review") if row["number_of_reviews"] else "No reviews yet"
    if group == "sentiment":
        return "Too few reviews to read their tone" if row["no_sentiment"] else "Tone of guest reviews"
    return {
        "room": row["room_type"],
        "property": f"Property type: {row['property_group']}",
        "neighbourhood": f"Neighbourhood: {row['neighbourhood_cleansed']}",
        "stay length": f"Stay length ({count(row['quote_nights'], 'night')})",
        "amenities": f"{int(row['n_amenities'])} amenities listed",
        "listing text": "Listing title and description",
    }[group]


def contribution_lists(explain, table):
    """Up to 5 [label, dollars] items plus "Everything else", adding up to fair - base."""
    feature_log = explain.filter(like="feature_log_")
    groups = [group_of(c.removeprefix("feature_log_")) for c in feature_log.columns]
    by_group = feature_log.T.groupby(np.array(groups)).sum().T
    fair = explain["en_reference_price"].to_numpy()
    base = explain["base_price"].to_numpy()
    log_steps = by_group.to_numpy()
    dollars = waterfall(base, log_steps)

    out = []
    for i in range(len(table)):
        biggest = np.argsort(-np.abs(log_steps[i]))[:5]  # same order as the waterfall
        items = [[label(by_group.columns[j], table.iloc[i]), round(dollars[i, j], 1)]
                 for j in biggest if abs(dollars[i, j]) >= 0.5]
        # The rest (smaller groups, the fold offset, rounding) goes here, so the list adds up.
        rest = fair[i] - base[i] - sum(value for _, value in items)
        out.append(json.dumps(items + [["Everything else", round(rest, 1)]]))
    return out


def build(city, snapshot):
    data = strfair.prepare(city, snapshot)
    S, F = data.sample, data.features  # same rows, same order; S has the name, URL and neighbourhood name
    ids = F["id"]
    scores = pd.read_csv(RESULTS / "scores" / f"{city}_{snapshot}.csv").set_index("listing_id").loc[ids]
    explain = pd.read_csv(RESULTS / "en_contributions" / f"{city}_{snapshot}.csv").set_index("listing_id").loc[ids]

    # Column names and order follow stub_scores.py. "interp" = Elastic net, "ens" = random forest.
    table = pd.DataFrame({
        "id": ids.astype("int64"),
        "city": city,
        "snapshot": snapshot,
        "name": S["name"].astype(str),
        "listing_url": S["listing_url"].astype(str),
        "latitude": F["latitude"],
        "longitude": F["longitude"],
        "neighbourhood_cleansed": S["neighbourhood_cleansed"].astype(str),
        "room_type": F["room_type"].astype(str),
        "property_group": F["property_group"].astype(str),
        "accommodates": F["accommodates"],
        "bedrooms": F["bedrooms"],
        "baths": F["baths"],
        "review_scores_rating": F["review_scores_rating"],
        "number_of_reviews": F["number_of_reviews"],
        "superhost": F["superhost"],
        "km_to_centre": F["km_to_centre"],
        "n_amenities": F["n_amenities"],
        "price": F["price"],
        "price_quote_checkin_date": pd.to_datetime(S["price_quote_checkin_date"]).dt.strftime("%Y-%m-%d"),
        "quote_nights": F["quote_nights"],
        "lead_days": F["lead_days"],
        "is_monthly_quote": F["is_monthly_quote"].fillna(0).astype(int),
        "fair_interp": scores["en_reference_price"].to_numpy(),
        "fair_ens": scores["rf_reference_price"].to_numpy(),
    })
    # The map turns ratios into labels with the band the reader picks, so no label column.
    table["ratio_interp"] = table["price"] / table["fair_interp"]
    table["ratio_ens"] = table["price"] / table["fair_ens"]
    table["base_price"] = explain["base_price"].to_numpy()

    # A few more columns for the card text only.
    text_columns = F[["host_listings_count", "nearest_attraction", "dist_to_nearest_attraction_km",
                      "has_license", "license_exempt"]].assign(no_sentiment=F["avg_sentiment"].isna())
    table["contributions"] = contribution_lists(explain, table.join(text_columns))

    sizes = strfair.impute_sizes(F[["room_type", "bedrooms", "beds", "baths"]])
    table["comps"] = comparables(table, sizes["bedrooms"])

    # The card must close: the items add up to fair_interp - base_price (to rounding).
    totals = table["contributions"].map(lambda s: sum(v for _, v in json.loads(s)))
    assert np.allclose(totals, table["fair_interp"] - table["base_price"], atol=0.051)

    folder = ROOT / "data" / "scored" / f"{city}_{snapshot}"
    folder.mkdir(parents=True, exist_ok=True)
    table.to_parquet(folder / "scored.parquet", index=False)
    base = table.groupby("is_monthly_quote")["base_price"].first()
    meta = {
        "city": city, "snapshot": snapshot, "n": len(table), "stub": False,  # stub: False = real models
        "base_price": {"nightly": base.get(0), "monthly": base.get(1)},
        "base_price_note": "geometric mean of the Elastic net out-of-fold fair prices with the same stay type",
        "models": {"fair_interp": "Elastic net", "fair_ens": "Random forest", "tuned_on": "June 2026",
                   "elastic_net": strfair.ENET_PARAMS, "random_forest": strfair.RF_PARAMS},
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=1, default=float))
    print(f"{city}: {len(table):,} listings written to {folder}")


if __name__ == "__main__":
    for city, snapshot in cities_to_run():
        build(city, snapshot)
