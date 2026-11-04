"""Feature lists and model builders for the two fair-price tracks.

Lists come from ``notebooks/05_feature_selection.ipynb`` (with sentiment).
Hyperparameters start as the untuned 04_baseline defaults; replace
``ENET_PARAMS`` / ``RF_PARAMS`` after tuning. ``scoring.py`` (separate) will
turn out-of-fold predictions into per-listing fair prices.
"""
from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


# Feature lists from 05_feature_selection (sentiment run)
# Shared candidates after leakage / near-constant drops. RF uses this list as-is.
CANDIDATES: list[str] = [
    "lead_days", "quote_nights", "weekend_checkin", "checkin_dow", "checkin_month",
    "is_monthly_quote", "lead_band", "has_discount", "discount_share", "minimum_nights",
    "min_nights_band", "room_type", "room", "property_group", "accommodates", "bedrooms",
    "beds", "shared_bath", "baths", "guests_per_bedroom", "guests_per_bed", "latitude",
    "longitude", "km_to_centre", "log_km_to_centre", "neighbourhood", "neighbourhood_group",
    "superhost", "host_listings_count", "calculated_host_listings_count",
    "calculated_host_listings_count_entire_homes", "calculated_host_listings_count_private_rooms",
    "log_host_listings", "multi_host", "single_listing_host", "host_entire_home_share",
    "host_years", "number_of_reviews", "log_reviews", "no_reviews", "tenure_months",
    "new_listing", "months_since_last_review", "review_scores_rating", "review_scores_accuracy",
    "review_scores_cleanliness", "review_scores_checkin", "review_scores_communication",
    "review_scores_location", "no_rating", "rating_filled", "name_len", "desc_len",
    "kw_luxury", "kw_view", "kw_renovated", "kw_cozy", "kw_walkable", "has_license",
    "license_exempt", "host_about_len", "maximum_nights", "n_amenities", "amg_tv_streaming",
    "amg_entertainment", "amg_outdoor_views", "amg_grill", "amg_luxury_recreation",
    "amg_cooking_appliances", "amg_climate_control", "amg_exercise_facilities", "amg_parking",
    "amg_laundry", "amg_fridge_freezer", "am_free_parking", "avg_sentiment", "sentiment_std",
    "negative_review_pct", "weighted_sentiment", "no_sentiment",
]

# Elastic net: one form of duplicates + VIF trim (avg_sentiment dropped; weighted_sentiment kept).
ENET_FEATURES: list[str] = [
    "lead_days", "quote_nights", "weekend_checkin", "checkin_dow", "checkin_month",
    "is_monthly_quote", "lead_band", "has_discount", "discount_share", "min_nights_band",
    "room_type", "property_group", "accommodates", "bedrooms", "beds", "shared_bath", "baths",
    "latitude", "longitude", "log_km_to_centre", "neighbourhood", "neighbourhood_group",
    "superhost", "host_listings_count", "calculated_host_listings_count_entire_homes",
    "calculated_host_listings_count_private_rooms", "log_host_listings", "host_entire_home_share",
    "host_years", "log_reviews", "tenure_months", "new_listing", "months_since_last_review",
    "review_scores_accuracy", "review_scores_cleanliness", "review_scores_checkin",
    "review_scores_communication", "review_scores_location", "no_rating", "rating_filled",
    "name_len", "desc_len", "kw_luxury", "kw_view", "kw_renovated", "kw_cozy", "kw_walkable",
    "has_license", "license_exempt", "host_about_len", "maximum_nights", "n_amenities",
    "amg_tv_streaming", "amg_entertainment", "amg_outdoor_views", "amg_grill",
    "amg_luxury_recreation", "amg_cooking_appliances", "amg_climate_control",
    "amg_exercise_facilities", "amg_parking", "amg_laundry", "amg_fridge_freezer",
    "am_free_parking", "sentiment_std", "negative_review_pct", "weighted_sentiment",
    "no_sentiment",
]

RF_FEATURES: list[str] = list(CANDIDATES)

# EN: from scripts/tune_elastic_net.py on Toronto 2026-09-16 (GroupKFold by host).
#     Slightly better than 04's alpha=0.001, l1_ratio=0.5 (MAE 0.2487 vs 0.2493).
#     Re-run on more cities before treating as final.
# RF: still 04_baseline defaults until RF search runs.
ENET_PARAMS: dict = {"alpha": 0.001, "l1_ratio": 0.15, "max_iter": 5000}
RF_PARAMS: dict = {"n_estimators": 300, "min_samples_leaf": 5, "n_jobs": -1, "random_state": 42}
ENET_TUNED: bool = True   
RF_TUNED: bool = False
TUNED: bool = False  



# Matrix helpers
def _ensure_no_sentiment(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    if "no_sentiment" not in out.columns and "avg_sentiment" in out.columns:
        out["no_sentiment"] = out["avg_sentiment"].isna().astype(int)
    for col in ("checkin_dow", "checkin_month"):
        if col in out.columns:
            out[col] = out[col].astype("object")
    return out


def feature_matrix(features: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Select model columns present in ``features`` (cities may lack neighbourhood_group)."""
    F = _ensure_no_sentiment(features)
    cols = [c for c in columns if c in F.columns]
    return F[cols].copy()


def _split_num_cat(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    cat = list(X.select_dtypes(exclude="number").columns)
    num = [c for c in X.columns if c not in cat]
    return num, cat



# Model builders (sklearn pipelines)
def make_elastic_net(X: pd.DataFrame, **overrides):
    """Elastic net on ``ENET_FEATURES``-style matrix. Numbers: median + scale; cats: one-hot."""
    params = {**ENET_PARAMS, **overrides}
    num, cat = _split_num_cat(X)
    pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), cat),
    ])
    return make_pipeline(pre, ElasticNet(**params))


def make_random_forest(X: pd.DataFrame, **overrides):
    """Random forest on ``RF_FEATURES``-style matrix. Numbers: median; cats: ordinal."""
    params = {**RF_PARAMS, **overrides}
    num, cat = _split_num_cat(X)
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), num),
        ("cat", make_pipeline(
            SimpleImputer(strategy="most_frequent"),
            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
        ), cat),
    ])
    return make_pipeline(pre, RandomForestRegressor(**params))
