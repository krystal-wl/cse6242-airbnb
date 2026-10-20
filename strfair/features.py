"""Feature engineering for the fair-price models.

Every builder takes the listings table returned by ``strfair.data.load_listings`` (any snapshot, any city)
and returns a DataFrame aligned on its index. Columns that a snapshot does not carry are simply skipped, so
the same code runs on the September 2025 schema (79 columns) and the 2026 schema (90 columns).

``build_features`` is the one-stop entry point. The ``amenities`` column is deliberately not used yet
(team decision, Oct 2026: work from the raw columns first).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------------------------------------
#: A "downtown" point per city for the distance-to-centre feature (lat, lon).
CITY_CENTRES: dict[str, tuple[float, float]] = {
    "new-york-city": (40.7580, -73.9855),    # Times Square
    "los-angeles": (34.0522, -118.2437),     # City Hall / downtown
    "toronto": (43.6453, -79.3806),          # Union Station
    "san-diego": (32.7157, -117.1611),       # Gaslamp Quarter
    "clark-county-nv": (36.1147, -115.1728), # the Strip (Bellagio)
    "jersey-city": (40.7169, -74.0333),      # Exchange Place PATH
    "boston": (42.3551, -71.0657),           # Boston Common
}

LISTING_KEYWORDS: dict[str, str] = {
    "kw_luxury": r"luxur|upscale|high-end|penthouse",
    "kw_view": r"\bview|skyline|ocean|waterfront",
    "kw_renovated": r"renovat|brand new|newly",
    "kw_cozy": r"\bcozy|cosy|charming",
    "kw_walkable": r"walk to|walking distance|steps (from|to)|close to",
}


# ---------------------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------------------
def haversine_km(lat: pd.Series, lon: pd.Series, lat0: float, lon0: float) -> pd.Series:
    lat1, lon1 = np.radians(lat.astype(float)), np.radians(lon.astype(float))
    dlat, dlon = lat1 - np.radians(lat0), lon1 - np.radians(lon0)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(np.radians(lat0)) * np.sin(dlon / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def _snapshot_date(df: pd.DataFrame) -> pd.Timestamp:
    if "snapshot" in df:
        return pd.to_datetime(df["snapshot"].iloc[0])
    return pd.to_datetime(df["last_scraped"]).min()


# ---------------------------------------------------------------------------------------------------------
# Feature families
# ---------------------------------------------------------------------------------------------------------
def target_and_quote_features(df: pd.DataFrame) -> pd.DataFrame:
    """Target (``price``, ``log_price``) and the anatomy of the quote behind it.

    2026 releases: the quote's check-in / check-out dates and the raw quote JSON (discounts, line items).
    September 2025 releases: ``price`` only, so the timing columns come out as NaN.
    """
    out = pd.DataFrame(index=df.index)
    out["price"] = df["price"].astype(float) if "price" in df else np.nan
    out["log_price"] = np.log(out["price"].where(out["price"] > 0))
    snap = _snapshot_date(df)

    if "price_quote_checkin_date" in df:
        ci = pd.to_datetime(df["price_quote_checkin_date"], errors="coerce")
        co = pd.to_datetime(df["price_quote_checkout_date"], errors="coerce")
        scraped = pd.to_datetime(df["last_scraped"], errors="coerce") if "last_scraped" in df else snap
        out["lead_days"] = (ci - scraped).dt.days
        out["quote_nights"] = (co - ci).dt.days
        out["weekend_checkin"] = ci.dt.dayofweek.isin([4, 5]).astype(float).where(ci.notna())
        out["checkin_dow"] = ci.dt.dayofweek
        out["checkin_month"] = ci.dt.month
        out["is_monthly_quote"] = (out["quote_nights"] >= 28).astype(float).where(out["quote_nights"].notna())
        # a few quotes have check-in a day or two before the listing's own scrape timestamp (multi-day
        # scrape); they belong with the same-day band rather than in a level of their own
        out["lead_band"] = pd.cut(out["lead_days"], [-10_000, 0, 7, 30, 90, 10_000],
                                  labels=["same_day", "1-7d", "8-30d", "31-90d", "90d+"]).astype("object")
    if "price_quote_raw" in df:
        def _quote(x):
            if not isinstance(x, str):
                return {}
            try:
                return json.loads(x).get("quote", {}) or {}
            except ValueError:
                return {}
        q = df["price_quote_raw"].map(_quote)
        disc = pd.to_numeric(q.map(lambda d: d.get("discount_amount")), errors="coerce")
        sub = pd.to_numeric(q.map(lambda d: d.get("discounted_subtotal")), errors="coerce")
        nightly_sub = pd.to_numeric(q.map(lambda d: d.get("nightly_subtotal")), errors="coerce")
        out["has_discount"] = disc.notna().astype(float).where(q.map(bool))
        out["discount_amount"] = disc
        gross = sub.add(disc, fill_value=0).where(sub.notna(), nightly_sub)
        out["discount_share"] = (disc / gross).where(disc.notna() & gross.gt(0), 0.0)
        nights = out["quote_nights"] if "quote_nights" in out else np.nan
        out["price_undiscounted"] = (gross / nights).where(gross.notna() & (nights > 0), out["price"])
        out["quote_total"] = pd.to_numeric(q.map(lambda d: d.get("total_price")), errors="coerce")
    if "minimum_nights" in df:
        mn = pd.to_numeric(df["minimum_nights"], errors="coerce")
        out["minimum_nights"] = mn
        out["min_nights_band"] = pd.cut(mn.fillna(1), [0, 1, 2, 6, 27, 100_000],
                                        labels=["1", "2", "3-6", "7-27", "28+"]).astype("object")
    return out


def size_features(df: pd.DataFrame) -> pd.DataFrame:
    """Room type, property type, capacity and bathrooms."""
    out = pd.DataFrame(index=df.index)
    if "room_type" in df:
        out["room_type"] = df["room_type"]
        out["room"] = df["room_type"].replace({"Hotel room": "Private room", "Shared room": "Private room"})
    if "property_type" in df:
        pt = df["property_type"].fillna("").astype(str)
        out["property_group"] = np.select(
            [pt.str.contains("hotel|hostel|boutique|aparthotel|resort|bed and breakfast", case=False),
             pt.str.contains("rental unit|condo|loft|serviced|apartment", case=False),
             pt.str.contains("home|house|townhouse|bungalow|cottage|villa|cabin|guesthouse|tiny", case=False)],
            ["hotel", "apartment", "house"], "other")
    for c in ("accommodates", "bedrooms", "beds"):
        if c in df:
            out[c] = pd.to_numeric(df[c], errors="coerce")
    if "bathrooms" in df or "bathrooms_text" in df:
        baths = pd.to_numeric(df["bathrooms"], errors="coerce") if "bathrooms" in df else pd.Series(np.nan, index=df.index)
        if "bathrooms_text" in df:
            txt = df["bathrooms_text"].fillna("").astype(str)
            from_text = pd.to_numeric(txt.str.extract(r"([\d.]+)")[0], errors="coerce")
            from_text = from_text.where(~txt.str.contains(r"^half-bath|^shared half", case=False), 0.5)
            baths = baths.fillna(from_text)
            out["shared_bath"] = txt.str.contains("shared", case=False).astype(int)
        out["baths"] = baths
    if {"accommodates", "bedrooms"} <= set(out.columns):
        out["guests_per_bedroom"] = out["accommodates"] / out["bedrooms"].clip(lower=1)
    if {"accommodates", "beds"} <= set(out.columns):
        out["guests_per_bed"] = out["accommodates"] / out["beds"].clip(lower=1)
    return out


def location_features(df: pd.DataFrame, city: str | None = None, min_neighbourhood_n: int = 20) -> pd.DataFrame:
    """Coordinates, distance to the city centre and pooled neighbourhood labels."""
    out = pd.DataFrame(index=df.index)
    city = city or (df["city"].iloc[0] if "city" in df else None)
    out["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    if city in CITY_CENTRES:
        lat0, lon0 = CITY_CENTRES[city]
        out["km_to_centre"] = haversine_km(out["latitude"], out["longitude"], lat0, lon0)
        out["log_km_to_centre"] = np.log1p(out["km_to_centre"])
    if "neighbourhood_cleansed" in df:
        hood = df["neighbourhood_cleansed"].fillna("Unknown").astype(str)
        counts = hood.value_counts()
        small = counts[counts < min_neighbourhood_n].index
        out["neighbourhood"] = hood.where(~hood.isin(small), "Other (small)")
        out["neighbourhood_raw"] = hood
    if "neighbourhood_group_cleansed" in df and df["neighbourhood_group_cleansed"].notna().any():
        out["neighbourhood_group"] = df["neighbourhood_group_cleansed"].fillna("Unknown").astype(str)
    return out


def host_features(df: pd.DataFrame) -> pd.DataFrame:
    """Host attributes that are still populated in the 2026 releases, plus the older ones when present."""
    out = pd.DataFrame(index=df.index)
    snap = _snapshot_date(df)
    if "host_is_superhost" in df:
        out["superhost"] = df["host_is_superhost"].map({True: 1, False: 0}).astype(float).fillna(0).astype(int)
    for c in ("host_identity_verified", "host_has_profile_pic", "instant_bookable"):
        if c in df and df[c].notna().any():
            out[c] = df[c].map({True: 1, False: 0}).astype(float).fillna(0).astype(int)
    for c in ("host_listings_count", "host_total_listings_count", "calculated_host_listings_count",
              "calculated_host_listings_count_entire_homes", "calculated_host_listings_count_private_rooms"):
        if c in df and df[c].notna().any():
            out[c] = pd.to_numeric(df[c], errors="coerce")
    if "calculated_host_listings_count" in out:
        n = out["calculated_host_listings_count"].fillna(1).clip(lower=1)
        out["log_host_listings"] = np.log1p(n)
        out["multi_host"] = (n >= 5).astype(int)
        out["single_listing_host"] = (n == 1).astype(int)
        if "calculated_host_listings_count_entire_homes" in out:
            out["host_entire_home_share"] = out["calculated_host_listings_count_entire_homes"].fillna(0) / n
    # tenure as a host: 2026 releases carry it directly; 2025 releases need host_since
    if "hosts_time_as_host_years" in df and df["hosts_time_as_host_years"].notna().any():
        out["host_years"] = (pd.to_numeric(df["hosts_time_as_host_years"], errors="coerce").fillna(0)
                             + pd.to_numeric(df.get("hosts_time_as_host_months"), errors="coerce").fillna(0) / 12)
    elif "host_since" in df and df["host_since"].notna().any():
        out["host_years"] = (snap - pd.to_datetime(df["host_since"], errors="coerce")).dt.days / 365.25
    for c in ("host_response_rate", "host_acceptance_rate"):
        if c in df and df[c].notna().any():
            out[c] = pd.to_numeric(df[c], errors="coerce")
    if "host_response_time" in df and df["host_response_time"].notna().any():
        order = {"within an hour": 0, "within a few hours": 1, "within a day": 2, "a few days or more": 3}
        out["host_response_time_ord"] = df["host_response_time"].map(order)
    return out


def review_features(df: pd.DataFrame) -> pd.DataFrame:
    """Review volume, recency, tenure and the rating sub-scores (with missing indicators)."""
    out = pd.DataFrame(index=df.index)
    snap = _snapshot_date(df)
    for c in ("number_of_reviews", "number_of_reviews_ltm", "number_of_reviews_l30d", "reviews_per_month"):
        if c in df:
            out[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "number_of_reviews" in out:
        out["log_reviews"] = np.log1p(out["number_of_reviews"])
        out["no_reviews"] = (out["number_of_reviews"] == 0).astype(int)
    if "number_of_reviews_ltm" in out:
        out["log_reviews_ltm"] = np.log1p(out["number_of_reviews_ltm"])
        out["active_ltm"] = (out["number_of_reviews_ltm"] > 0).astype(int)
    if "first_review" in df:
        fr = pd.to_datetime(df["first_review"], errors="coerce")
        out["tenure_months"] = ((snap - fr).dt.days / 30.44).clip(lower=0).fillna(0)
        out["new_listing"] = (out["tenure_months"] < 12).astype(int)
    if "last_review" in df:
        lr = pd.to_datetime(df["last_review"], errors="coerce")
        out["months_since_last_review"] = ((snap - lr).dt.days / 30.44).clip(lower=0)
    score_cols = [c for c in df.columns if c.startswith("review_scores_")]
    for c in score_cols:
        s = pd.to_numeric(df[c], errors="coerce")
        out[c] = s
    if "review_scores_rating" in out:
        out["no_rating"] = out["review_scores_rating"].isna().astype(int)
        out["rating_filled"] = out["review_scores_rating"].fillna(out["review_scores_rating"].median())
    return out


def listing_text_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cheap features from the listing's own text and regulatory fields (not the reviews)."""
    out = pd.DataFrame(index=df.index)
    if "name" in df:
        out["name_len"] = df["name"].fillna("").astype(str).str.len()
    if "description" in df:
        desc = df["description"].fillna("").astype(str)
        out["desc_len"] = desc.str.len()
        out["has_description"] = (out["desc_len"] > 0).astype(int)
        text = (df["name"].fillna("").astype(str) + " " + desc).str.lower() if "name" in df else desc.str.lower()
        for col, pat in LISTING_KEYWORDS.items():
            out[col] = text.str.contains(pat, regex=True).astype(int)
    if "neighborhood_overview" in df:
        out["has_neighborhood_overview"] = df["neighborhood_overview"].notna().astype(int)
    if "license" in df:
        lic = df["license"].fillna("").astype(str).str.strip()
        out["has_license"] = (lic != "").astype(int)
        out["license_exempt"] = lic.str.contains("exempt", case=False).astype(int)
    if "host_about" in df:
        out["host_about_len"] = df["host_about"].fillna("").astype(str).str.len()
    return out


def availability_features(df: pd.DataFrame) -> pd.DataFrame:
    """Availability / demand proxies. Kept separate because they are *responses* to price (see docs/features.md):
    use them for validation of the labels, not as inputs to the benchmark models."""
    out = pd.DataFrame(index=df.index)
    for c in ("availability_30", "availability_60", "availability_90", "availability_365", "availability_eoy",
              "estimated_occupancy_l365d", "estimated_revenue_l365d", "minimum_nights_avg_ntm",
              "maximum_nights_avg_ntm", "maximum_nights"):
        if c in df:
            out[c] = pd.to_numeric(df[c], errors="coerce")
    if "has_availability" in df:
        out["has_availability"] = df["has_availability"].map({True: 1, False: 0}).astype(float)
    if "availability_30" in out:
        out["unavail_share_30"] = 1 - out["availability_30"] / 30
    return out


# ---------------------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------------------
ID_COLS = ["id", "city", "snapshot"]


def build_features(df: pd.DataFrame, city: str | None = None, include_availability: bool = True) -> pd.DataFrame:
    """All feature families side by side, keyed by ``id`` / ``city`` / ``snapshot``.

    Rows without a price are kept (price is NaN) so the same table can be used to score unpriced listings.
    The ``amenities`` column is not used (team decision, Oct 2026: work from the raw columns first).
    """
    parts = [df[[c for c in ID_COLS if c in df]].copy(),
             target_and_quote_features(df),
             size_features(df),
             location_features(df, city),
             host_features(df),
             review_features(df),
             listing_text_features(df)]
    if include_availability:
        parts.append(availability_features(df))
    out = pd.concat(parts, axis=1)
    return out.loc[:, ~out.columns.duplicated()]


FAMILIES = {
    "target_quote": target_and_quote_features, "size": size_features, "location": location_features,
    "host": host_features, "reviews": review_features,
    "listing_text": listing_text_features, "availability": availability_features,
}


def feature_families(df: pd.DataFrame) -> pd.Series:
    """Map every feature column produced for ``df`` to the family (builder) it came from."""
    fam = {}
    for name, fn in FAMILIES.items():
        for c in fn(df).columns:
            fam.setdefault(c, name)
    return pd.Series(fam, name="family")


CATEGORICAL = ["room", "room_type", "property_group", "neighbourhood", "neighbourhood_group", "lead_band",
               "min_nights_band"]
