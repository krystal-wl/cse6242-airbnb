"""Placeholder scores so the map can be built before the modelling notebooks deliver.

Writes ``data/scored/<city>_<snapshot>/scored.parquet`` in the contract format of ``docs/map_design.md``
§5. The models here are deliberately small (ridge on log price and a modest random forest, both scored
out-of-fold with a seeded 5-fold split) and are **not** the team's models: the modelling notebooks replace
this file's output column for column, and ``scripts/build_map_data.py`` reads only that contract.

    python scripts/stub_scores.py san-diego                 # pinned snapshot
    python scripts/stub_scores.py new-york-city 2026-03-16  # the March stability snapshot
    python scripts/stub_scores.py --all                     # every pinned + stability snapshot

Contract columns written (one row per in-sample listing):
    identity     id, name, listing_url, latitude, longitude, neighbourhood_cleansed
    attributes   room_type, accommodates, bedrooms, baths, review_scores_rating, number_of_reviews,
                 superhost, km_to_centre
    quote        price, price_quote_checkin_date, quote_nights, lead_days, is_monthly_quote
    scores       fair_interp, fair_ens (dollars per night, out-of-fold), ratio_interp, ratio_ens
    explanation  contributions: JSON list of [name, usd], the 5 largest by |usd| plus ["Everything else", usd],
                 summing to fair_interp - base_price (the city's typical listing of the same stay type)
    comparables  comps: JSON list of up to 5 listing ids (same room type and stay type, bedrooms within 1,
                 nearest within 1 km, widened to 3 km, then nearest)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import strfair  # noqa: E402

SCORED_DIR = REPO_ROOT / "data" / "scored"
SEED = 42
BASE_PRICE_NOTE = "geometric mean of in-sample prices with the same stay type (nightly / monthly)"

# Readable names for the contribution rows. Columns not listed fall back to the column name.
NUMERIC_FEATURES = [
    "accommodates", "bedrooms", "beds", "baths", "shared_bath", "log_km_to_centre", "superhost",
    "log_host_listings", "log_reviews", "no_reviews", "rating_filled", "no_rating", "tenure_months",
    "lead_days", "weekend_checkin", "log_quote_nights", "is_monthly_quote", "log_minimum_nights",
    "n_amenities", "has_license", "kw_luxury", "kw_view", "kw_renovated", "kw_cozy", "kw_walkable",
    "amg_entertainment", "amg_outdoor_views", "amg_luxury_recreation", "amg_kitchen_dining", "amg_family_pet",
    "amg_exercise", "amg_parking", "amg_bathroom_laundry", "amg_connectivity",
    "am_wifi", "am_free_parking", "am_smoking_allowed", "am_breakfast",
    "bedrooms_missing", "beds_missing", "baths_missing",
]
CATEGORICAL_FEATURES = ["room", "property_group", "neighbourhood"]

#: contribution group per column prefix; one-hot levels of a categorical fold into one group
GROUPS: dict[str, str] = {
    "accommodates": "size", "bedrooms": "size", "beds": "size", "baths": "size", "shared_bath": "size",
    "bedrooms_missing": "size", "beds_missing": "size", "baths_missing": "size",
    "log_km_to_centre": "distance", "neighbourhood": "neighbourhood", "room": "room", "property_group": "property",
    "superhost": "host", "log_host_listings": "host",
    "log_reviews": "reviews", "no_reviews": "reviews", "rating_filled": "rating", "no_rating": "rating",
    "tenure_months": "reviews",
    "lead_days": "quote timing", "weekend_checkin": "quote timing", "log_quote_nights": "stay length",
    "is_monthly_quote": "stay length", "log_minimum_nights": "stay length",
    "n_amenities": "amenities", "has_license": "licence",
    "kw_luxury": "listing text", "kw_view": "listing text", "kw_renovated": "listing text", "kw_cozy": "listing text",
    "kw_walkable": "listing text",
}
AMENITY_NAMES = {
    "amg_entertainment": "Entertainment amenities", "amg_outdoor_views": "Outdoor space / views",
    "amg_luxury_recreation": "Pool, hot tub or gym", "amg_kitchen_dining": "Kitchen & dining",
    "amg_family_pet": "Family / pet friendly", "amg_exercise": "Exercise equipment", "amg_parking": "Parking",
    "amg_bathroom_laundry": "Laundry & bathroom", "amg_connectivity": "Wi-Fi & workspace",
    "am_wifi": "Wi-Fi", "am_free_parking": "Free parking", "am_smoking_allowed": "Smoking allowed",
    "am_breakfast": "Breakfast",
}


def _group_of(col: str) -> str:
    if col in AMENITY_NAMES:
        return col
    for prefix, group in GROUPS.items():
        if col == prefix or col.startswith(prefix + "="):
            return group
    return col


def _group_label(group: str, row: pd.Series) -> str:
    """A reader-facing name for a contribution group, using the listing's own values."""
    def num(c, nd=0):
        v = row.get(c)
        return None if v is None or pd.isna(v) else (int(round(v)) if nd == 0 else round(float(v), nd))

    if group == "size":
        parts = [f"sleeps {num('accommodates')}"]
        if num("bedrooms") is not None:
            parts.append(f"{num('bedrooms')} bed" + ("rooms" if num("bedrooms") != 1 else "room"))
        if num("baths", 1) is not None:
            parts.append(f"{num('baths', 1):g} bath" + ("s" if num("baths", 1) != 1 else ""))
        return "Size: " + ", ".join(parts)
    if group == "distance":
        return f"{round(float(row.get('km_to_centre', 0)), 1)} km from the centre"
    if group == "neighbourhood":
        return f"Neighbourhood: {row.get('neighbourhood_cleansed', '')}"
    if group == "room":
        return str(row.get("room_type", "Room type"))
    if group == "property":
        return f"Property type: {row.get('property_group', '')}"
    if group == "host":
        return "Host: superhost" if row.get("superhost", 0) == 1 else "Host profile"
    if group == "reviews":
        n = num("number_of_reviews")
        return "No reviews yet" if not n else f"{n} reviews"
    if group == "rating":
        r = row.get("review_scores_rating")
        return "No rating yet" if r is None or pd.isna(r) else f"Rating {float(r):.2f}"
    if group == "quote timing":
        return f"Quote timing ({num('lead_days')} days ahead)"
    if group == "stay length":
        n = num("quote_nights")
        return f"Stay length ({n} nights)" if n else "Stay length"
    if group == "amenities":
        return f"{num('n_amenities')} amenities listed"
    if group == "licence":
        return "Licence on file"
    if group == "listing text":
        return "Listing description"
    return AMENITY_NAMES.get(group, group)


def design_matrix(F: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Numeric design matrix for the stub models plus the (imputed) size columns used for comps."""
    X = pd.DataFrame(index=F.index)
    sizes = strfair.impute_sizes(F[["room_type", "bedrooms", "beds", "baths"]])
    for c in ("bedrooms", "beds", "baths", "bedrooms_missing", "beds_missing", "baths_missing"):
        X[c] = sizes[c] if c in sizes else 0
    F = F.assign(
        log_quote_nights=np.log1p(pd.to_numeric(F.get("quote_nights"), errors="coerce")),
        log_minimum_nights=np.log1p(pd.to_numeric(F.get("minimum_nights"), errors="coerce")),
    )
    for c in NUMERIC_FEATURES:
        if c in X or c not in F:
            continue
        X[c] = pd.to_numeric(F[c], errors="coerce")
    if "lead_days" in X:
        X["lead_days"] = X["lead_days"].clip(0, 365)
    X = X.fillna(X.median(numeric_only=True)).fillna(0)
    for c in CATEGORICAL_FEATURES:
        if c in F:
            d = pd.get_dummies(F[c].astype(str), prefix=c, prefix_sep="=", dtype=float)
            X = pd.concat([X, d], axis=1)
    return X, sizes


def oof_predictions(X: pd.DataFrame, y: pd.Series, latlon: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, object, object]:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X_rf = pd.concat([X, latlon], axis=1)
    interp = np.zeros(len(X))
    ens = np.zeros(len(X))
    for tr, te in KFold(5, shuffle=True, random_state=SEED).split(X):
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=3.0)).fit(X.iloc[tr], y.iloc[tr])
        interp[te] = ridge.predict(X.iloc[te])
        rf = RandomForestRegressor(n_estimators=120, min_samples_leaf=3, max_features=0.4, n_jobs=-1,
                                   random_state=SEED).fit(X_rf.iloc[tr], y.iloc[tr])
        ens[te] = rf.predict(X_rf.iloc[te])
    full = make_pipeline(StandardScaler(), Ridge(alpha=3.0)).fit(X, y)
    return interp, ens, full, X_rf


def contributions(X: pd.DataFrame, full_ridge, fair: np.ndarray, base: np.ndarray, rows: pd.DataFrame) -> list[str]:
    """Top-5 grouped contributions in dollars per listing, closing exactly on fair - base (base per listing)."""
    scaler, ridge = full_ridge.named_steps["standardscaler"], full_ridge.named_steps["ridge"]
    Z = (X.values - scaler.mean_) / np.where(scaler.scale_ == 0, 1, scaler.scale_)
    C = Z * ridge.coef_  # log-price contribution per column
    groups = [_group_of(c) for c in X.columns]
    uniq = sorted(set(groups))
    idx = {g: [i for i, gg in enumerate(groups) if gg == g] for g in uniq}
    G = np.column_stack([C[:, idx[g]].sum(axis=1) for g in uniq])  # per-group log contributions
    out = []
    for i in range(len(X)):
        logs = G[i]
        total = logs.sum()
        gap = float(fair[i] - base[i])
        usd = logs * (gap / total) if abs(total) > 1e-9 else np.zeros_like(logs)
        order = np.argsort(-np.abs(usd))
        top = order[:5]
        rest = float(usd[order[5:]].sum())
        row = rows.iloc[i]
        items = [[_group_label(uniq[j], row), round(float(usd[j]), 1)] for j in top if abs(usd[j]) >= 0.5]
        items.append(["Everything else", round(rest + sum(float(usd[j]) for j in top if abs(usd[j]) < 0.5), 1)])
        out.append(json.dumps(items))
    return out


def comparables(S: pd.DataFrame, bedrooms: pd.Series, k: int = 5) -> list[str]:
    from sklearn.neighbors import BallTree

    ids = S["id"].to_numpy()
    comps = [None] * len(S)
    key = S["room_type"].astype(str) + "|" + S["is_monthly_quote"].fillna(0).astype(int).astype(str)
    coords = np.radians(S[["latitude", "longitude"]].to_numpy(dtype=float))
    beds = bedrooms.to_numpy(dtype=float)
    for _, members in key.groupby(key).groups.items():
        pos = S.index.get_indexer(members)
        if len(pos) < 2:
            for p in pos:
                comps[p] = "[]"
            continue
        tree = BallTree(coords[pos], metric="haversine")
        kk = min(60, len(pos))
        dist, nn = tree.query(coords[pos], k=kk)
        dist_km = dist * 6371.0
        for r, p in enumerate(pos):
            cand = [(dist_km[r, j], pos[nn[r, j]]) for j in range(kk)
                    if pos[nn[r, j]] != p and abs(beds[pos[nn[r, j]]] - beds[p]) <= 1]
            chosen = [q for d, q in cand if d <= 1.0][:k]
            if len(chosen) < k:
                chosen = [q for d, q in cand if d <= 3.0][:k]
            if len(chosen) < k:
                chosen = [q for d, q in cand][:k]
            comps[p] = json.dumps([int(ids[q]) for q in chosen])
    return comps


def score(city: str, snapshot: str) -> Path:
    t0 = time.time()
    data = strfair.prepare(city, snapshot)
    S, F = data.sample, data.features
    X, sizes = design_matrix(F)
    y = F["log_price"]
    latlon = F[["latitude", "longitude"]].astype(float).fillna(0)
    interp, ens, full_ridge, _ = oof_predictions(X, y, latlon)
    fair_interp, fair_ens = np.exp(interp), np.exp(ens)
    # the "typical listing" the waterfall starts from: the geometric mean price of the same stay type, because
    # monthly quotes sit at about half the nightly level and would otherwise dominate the base in NYC
    stay = F["is_monthly_quote"].fillna(0).astype(int)
    base_by_stay = np.exp(y.groupby(stay).mean())
    base = stay.map(base_by_stay).to_numpy(dtype=float)

    out = pd.DataFrame({
        "id": S["id"].to_numpy(),
        "city": city, "snapshot": snapshot,
        "name": S["name"].astype(str).to_numpy(),
        "listing_url": S["listing_url"].astype(str).to_numpy(),
        "latitude": F["latitude"].astype(float).to_numpy(),
        "longitude": F["longitude"].astype(float).to_numpy(),
        "neighbourhood_cleansed": S["neighbourhood_cleansed"].astype(str).to_numpy(),
        "room_type": F["room_type"].astype(str).to_numpy(),
        "property_group": F["property_group"].astype(str).to_numpy(),
        "accommodates": F["accommodates"].to_numpy(),
        "bedrooms": F["bedrooms"].to_numpy(),
        "baths": F["baths"].to_numpy(),
        "review_scores_rating": F["review_scores_rating"].to_numpy(),
        "number_of_reviews": F["number_of_reviews"].to_numpy(),
        "superhost": F["superhost"].to_numpy(),
        "km_to_centre": F["km_to_centre"].to_numpy(),
        "n_amenities": F["n_amenities"].to_numpy() if "n_amenities" in F else np.nan,
        "price": F["price"].to_numpy(),
        "price_quote_checkin_date": pd.to_datetime(S["price_quote_checkin_date"], errors="coerce").dt.strftime("%Y-%m-%d").to_numpy(),
        "quote_nights": F["quote_nights"].to_numpy(),
        "lead_days": F["lead_days"].to_numpy(),
        "is_monthly_quote": F["is_monthly_quote"].fillna(0).astype(int).to_numpy(),
        "fair_interp": fair_interp, "fair_ens": fair_ens,
    }, index=S.index)
    out["ratio_interp"] = out["price"] / out["fair_interp"]
    out["ratio_ens"] = out["price"] / out["fair_ens"]
    out["contributions"] = contributions(X, full_ridge, fair_interp, base, out)
    out["comps"] = comparables(out, sizes["bedrooms"])
    out["base_price"] = base

    dest = SCORED_DIR / f"{city}_{snapshot}"
    dest.mkdir(parents=True, exist_ok=True)
    out.reset_index(drop=True).to_parquet(dest / "scored.parquet", index=False)
    (dest / "meta.json").write_text(json.dumps({
        "city": city, "snapshot": snapshot, "n": int(len(out)),
        "base_price": {"nightly": float(base_by_stay.get(0, np.nan)), "monthly": float(base_by_stay.get(1, np.nan))},
        "base_price_note": BASE_PRICE_NOTE, "stub": True, "code": data.meta.get("code"), "data": data.meta.get("data"),
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=1))

    band = 0.2
    lab = np.where(out["ratio_interp"] < 1 - band, "under", np.where(out["ratio_interp"] > 1 + band, "over", "fair"))
    mae_i = float(np.median(np.abs(out["price"] - out["fair_interp"])))
    mae_e = float(np.median(np.abs(out["price"] - out["fair_ens"])))
    shares = pd.Series(lab).value_counts(normalize=True).round(3).to_dict()
    print(f"{city} {snapshot} | {len(out):,} listings | median |err| ${mae_i:.0f} interp, ${mae_e:.0f} ens | "
          f"labels at ±{band:.0%}: {shares} | {time.time() - t0:.0f}s -> {dest / 'scored.parquet'}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("city", nargs="?")
    ap.add_argument("snapshot", nargs="?")
    ap.add_argument("--all", action="store_true", help="every pinned snapshot plus the March stability snapshots")
    args = ap.parse_args()
    if args.all:
        jobs = list(strfair.PINNED_SNAPSHOTS.items()) + list(strfair.STABILITY_SNAPSHOTS.items())
    elif args.city:
        jobs = [(args.city, args.snapshot or strfair.PINNED_SNAPSHOTS[args.city])]
    else:
        ap.error("give a city or --all")
    for city, snap in jobs:
        score(city, snap)


if __name__ == "__main__":
    main()
