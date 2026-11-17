"""strfair: shared code for the CSE 6242 "price fairness in short-term rentals" project.

What a model notebook needs is two lines::

    import strfair
    data = strfair.prepare("toronto", "2026-06-15")   # city + snapshot from the notebook's first cell
    data.listings, data.sample, data.features, data.reviews, data.calendar, data.neighbourhoods, data.geojson

- ``strfair.config``   what the data is: pinned snapshots + sha256, schema, which listings are in the sample
- ``strfair.prep``     ``prepare()``: verify, type, mark the sample, build the standard features; cached, fingerprinted
- ``strfair.data``     find snapshots under data/<city>/<date>/ and load the Inside Airbnb files
- ``strfair.features`` feature builders (one per family) plus the ``LEAKY`` / ``DEMAND_RESPONSE`` reference lists
"""
from strfair import config  # noqa: F401
from strfair.config import PINNED_SNAPSHOTS, STABILITY_SNAPSHOTS, VERSION  # noqa: F401
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
from strfair.features import (  # noqa: F401
    CATEGORICAL,
    CITY_CENTRES,
    DEMAND_RESPONSE,
    ID_COLUMNS,
    LEAKY,
    amenity_features,
    build_features,
    feature_families,
)
from strfair.tourist import ATTRACTIONS, tourist_features  # noqa: F401
from strfair.models import (  # noqa: F401
    CANDIDATES,
    ENET_FEATURES,
    ENET_PARAMS,
    ENET_TUNED,
    RF_FEATURES,
    RF_PARAMS,
    RF_TUNED,
    TUNED,
    feature_matrix,
    make_elastic_net,
    make_random_forest,
)
from strfair.prep import CityData, build, fingerprint, impute_sizes, prepare  # noqa: F401

__version__ = "0.2.0"
