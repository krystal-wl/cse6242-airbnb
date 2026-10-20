"""strfair: shared code for the CSE 6242 "price fairness in short-term rentals" project.

- ``strfair.data``     find snapshots under data/<city>/<date>/ and load the Inside Airbnb files
- ``strfair.features`` turn a listings table into model-ready features

The helpers in ``data`` were lifted from ``notebooks/01_load_city_starter.ipynb`` (same behaviour); the
feature builders generalise the Albany pilot script to every project city.
"""
from strfair.data import (  # noqa: F401
    DATA_DIR,
    PARTIAL_SNAPSHOTS,
    PROJECT_CITIES,
    REPO_ROOT,
    available_cities,
    data_inventory,
    describe_columns,
    is_partial,
    list_snapshots,
    load_all_snapshots,
    load_calendar,
    load_geojson,
    load_listings,
    load_listings_summary,
    load_neighbourhoods,
    load_reviews,
    parse_price,
    price_coverage,
    priced_snapshots,
    snapshot_dir,
)
from strfair.features import CITY_CENTRES, build_features  # noqa: F401

__version__ = "0.1.0"
