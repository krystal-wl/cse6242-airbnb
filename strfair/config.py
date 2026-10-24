"""What "the data" is, in one file: which raw files, and which of their rows count.

``strfair.prep`` reads its decisions from here and nowhere else. Nothing below is about modelling: no
feature list, no split, no imputation, no encoders. Those are each notebook's own choices. A notebook picks
the city and the snapshot (its first cell); this file says which bytes that snapshot must be and which
listings are in the sample. Change a value, bump ``VERSION``, open a PR; everyone rebuilds and compares
fingerprints.
"""
from __future__ import annotations

VERSION = "v1"  # cached output goes to data/processed/<VERSION>/

# =========================================================================================================
# 1. The snapshots the team works from
# =========================================================================================================
#: The agreed snapshot per city. ``prepare(city, snapshot)`` accepts any downloaded date, but warns when the
#: date is not this one, so a notebook cannot drift to "latest" by accident (Inside Airbnb adds a snapshot
#: every quarter).
PINNED_SNAPSHOTS: dict[str, str] = {
    "new-york-city":   "2026-06-14",
    "los-angeles":     "2026-06-15",
    "toronto":         "2026-06-15",
    "san-diego":       "2026-06-27",
    "clark-county-nv": "2026-06-27",
    "jersey-city":     "2026-06-27",
}

#: The earlier 2026 release of the three cities that have one: for the March-vs-June stability check
#: (docs/models.md §3). Toronto's is a partial scrape (28% of listings missing): fine per listing, never for
#: counts.
STABILITY_SNAPSHOTS: dict[str, str] = {
    "new-york-city": "2026-03-16",
    "los-angeles":   "2026-03-16",
    "toronto":       "2026-03-19",
}

#: sha256 of ``listings.csv.gz`` as published, copied from the ``manifest.json`` the downloader writes.
#: ``prepare`` compares the local file against this when the snapshot is listed here.
LISTINGS_SHA256: dict[tuple[str, str], str] = {
    ("new-york-city",   "2026-06-14"): "10eb56b21ec71a838b30ef47b836f3d375269baeed5ff9e5c35ff3c6a98d3ca7",
    ("los-angeles",     "2026-06-15"): "ebc99e8a5ff2f60cbd91323571c2bdf1f8c2c74fe3ac9669d7c9a24d2294dec5",
    ("toronto",         "2026-06-15"): "175b9d6efa701837ef768a5f71256f845dc92c80bf67cbe071d8e3830a8fb9cc",
    ("san-diego",       "2026-06-27"): "de360747802aa61a094e20e74f3e4f4e15c94f365a33c3acfb8ab106c89bb414",
    ("clark-county-nv", "2026-06-27"): "447347e406a992d49d63704daf71539bf87823ac29ff29e9fd42ff81af242307",
    ("jersey-city",     "2026-06-27"): "9d48073e30b0ed7309ed46fa05af1b31c25b8cf1caa3eb494627e2c33770e91b",
    ("new-york-city",   "2026-03-16"): "13b4f036bff80bcf6df26d732b3f96059827022110e09bdb6696ac3c6581baad",
    ("los-angeles",     "2026-03-16"): "ffdef08afe58b62e57cffb9da0f1daa97bf76e223fe98ce9e2022dd330976fc6",
    ("toronto",         "2026-03-19"): "344a596fef35bbf885c477d1b21fc34b7b90f93b446da8e935db248817a57bde",
}

# =========================================================================================================
# 2. Which listings are in the sample
# =========================================================================================================
#: Raw columns every 2026 snapshot must carry (Isabelle's ``column_checker``, applied to the one snapshot
#: being prepared). ``prepare`` fails loudly when one is missing, so a schema change cannot pass silently.
SCHEMA_COLS: list[str] = [
    "id", "price", "latitude", "longitude", "room_type", "accommodates",
    "property_type", "bathrooms", "bathrooms_text", "bedrooms", "beds", "amenities",
    "neighbourhood_cleansed", "minimum_nights", "number_of_reviews", "first_review", "last_review",
    "review_scores_rating", "host_is_superhost", "calculated_host_listings_count", "last_scraped",
    "price_quote_checkin_date", "price_quote_checkout_date", "price_quote_raw",
]

#: A listing is in the sample when these raw columns are present (Isabelle's ``needed_factors``, with
#: ``price`` in place of ``price_quote_price_per_night``: identical in 2026 releases) ...
REQUIRED_RAW_COLS: list[str] = ["id", "price", "latitude", "longitude", "room_type", "accommodates"]

#: ... and its price is in this range (docs/features.md §1.2). Everything else stays in ``listings`` with
#: ``in_sample = False``.
PRICE_MIN: float = 10.0
PRICE_MAX: float = 10_000.0

#: 28+ night quotes (77% of NYC, 54% Toronto, 46% LA) are in the sample; models control for the quote
#: length (docs/features.md §1.2). Flip only with a VERSION bump.
DROP_MONTHLY_QUOTES: bool = False
