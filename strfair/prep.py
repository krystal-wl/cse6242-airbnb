"""One call per notebook: ``strfair.prepare(city, snapshot)``.

The notebook's first cell names the city and the snapshot. This module does the part everyone shares
(``strfair.config``: verify the raw file, type it, mark the sample) and returns one DataFrame per Inside
Airbnb file:

    data = strfair.prepare("toronto", "2026-06-15")
    data.listings        # every listing of the snapshot, typed, with an ``in_sample`` flag
    data.sample          # the in-sample rows of ``listings`` (what the models are fitted on)
    data.features        # optional starting point: the standard feature families built from ``sample``
    data.reviews         # (listing_id, date) for every review; ``data.reviews_text`` adds the comments
    data.calendar        # 365 days x listings (loaded on first access: 11 M rows for NYC)
    data.neighbourhoods  # neighbourhood lookup; ``data.geojson`` the polygons

Everything after that (which features, how to split or cross-validate, how to impute, which model) is the
notebook's own. ``features`` is a convenience, not a contract: build your own from ``sample`` or add
columns to it. ``impute_sizes`` is an optional helper for the size columns.

Steps: verify sha256 -> load and type the listings -> schema check -> mark the sample (price present and
in range, required columns present) -> build the standard features for the sample -> cache as parquet ->
fingerprint. The cache lives under ``data/processed/<VERSION>/<city>_<snapshot>/`` and is rebuilt whenever
this package's source changes, so two people on the same commit get byte-identical files. Compare the
``data`` fingerprint that ``prepare`` prints: same string, same ``listings``.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from functools import cached_property
from pathlib import Path

import pandas as pd

from strfair import config as C
from strfair.data import (DATA_DIR, is_partial, list_snapshots, load_calendar, load_geojson, load_listings,
                          load_listings_summary, load_neighbourhoods, load_reviews, priced_snapshots, snapshot_dir)
from strfair.features import build_features

PROCESSED_DIR = DATA_DIR / "processed"
_SOURCE_FILES = ["config.py", "data.py", "features.py", "amenities.py", "prep.py"]


# ---------------------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_hash() -> str:
    """Short hash of this package's source: part of the cache key and of the fingerprint line."""
    h = hashlib.sha1()
    for name in _SOURCE_FILES:
        h.update((Path(__file__).parent / name).read_bytes())
    return h.hexdigest()[:8]


def fingerprint(df: pd.DataFrame) -> str:
    """Short, machine-independent hash of a frame's values (column names, order and content)."""
    cols = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s) or str(s.dtype) == "boolean":
            cols[c] = s.astype("float64")
        elif pd.api.types.is_numeric_dtype(s):
            cols[c] = s.astype("float64").round(6)
        else:  # strings, categories, datetimes: their text form
            cols[c] = s.where(s.notna(), "").astype(str)
    norm = pd.DataFrame(cols, index=df.index)
    h = hashlib.sha1()
    h.update(",".join(df.columns).encode())
    h.update(pd.util.hash_pandas_object(norm, index=False).values.tobytes())
    return h.hexdigest()[:8]


def _to_parquet(df: pd.DataFrame, path: Path) -> None:
    with warnings.catch_warnings():  # pyarrow 11 + pandas 2.x deprecation chatter, not ours
        warnings.simplefilter("ignore", DeprecationWarning)
        df.to_parquet(path, index=False)


def _read_parquet(path: Path) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return pd.read_parquet(path)


# ---------------------------------------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------------------------------------
def _check_raw(city: str, snapshot: str, strict: bool) -> None:
    folder = snapshot_dir(city, snapshot)
    expected = C.LISTINGS_SHA256.get((city, snapshot))
    if expected is None:
        agreed = C.PINNED_SNAPSHOTS.get(city)
        warnings.warn(f"{city} {snapshot} is not a team snapshot (agreed: {agreed}; stability check: "
                      f"{C.STABILITY_SNAPSHOTS.get(city, 'none')}). Results will not match anyone else's.",
                      stacklevel=3)
    else:
        actual = _sha256(folder / "listings.csv.gz")
        if actual != expected:
            msg = (f"{folder / 'listings.csv.gz'} has sha256 {actual[:12]}..., expected {expected[:12]}... "
                   f"Re-download it: python scripts/download_data.py {city}@{snapshot} --files listings --force")
            if strict:
                raise ValueError(msg)
            warnings.warn(msg, stacklevel=3)
    if is_partial(city, snapshot):
        warnings.warn(f"{city} {snapshot} is a partial scrape: fine per listing, do not use it for counts.",
                      stacklevel=3)


def _check_schema(df: pd.DataFrame, city: str, snapshot: str, strict: bool) -> None:
    missing = [c for c in C.SCHEMA_COLS if c not in df.columns]
    if not missing:
        return
    msg = (f"{city} {snapshot} lacks {len(missing)} expected column(s): {missing}. "
           "2025 releases have no price_quote_* columns and their price is a different measure "
           "(docs/features.md §1.3); the team works from 2026 snapshots.")
    if strict:
        raise ValueError(msg)
    warnings.warn(msg, stacklevel=3)


def _sample_mask(df: pd.DataFrame) -> pd.Series:
    keep = df[[c for c in C.REQUIRED_RAW_COLS if c in df]].notna().all(axis=1)
    keep &= df["price"].between(C.PRICE_MIN, C.PRICE_MAX)
    if C.DROP_MONTHLY_QUOTES and {"price_quote_checkin_date", "price_quote_checkout_date"} <= set(df.columns):
        nights = (df["price_quote_checkout_date"] - df["price_quote_checkin_date"]).dt.days
        keep &= ~(nights >= 28)
    return keep


def build(city: str, snapshot: str, strict: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(listings, features) for one snapshot, straight from the raw file (no cache)."""
    _check_raw(city, snapshot, strict)
    listings = load_listings(city, snapshot)
    _check_schema(listings, city, snapshot, strict)
    if listings["id"].duplicated().any():
        raise ValueError(f"{city} {snapshot}: duplicated listing ids")
    listings["in_sample"] = _sample_mask(listings)
    if not listings["in_sample"].any():
        raise ValueError(f"{city} {snapshot} has no listing with a usable price (Inside Airbnb shipped empty "
                         f"price columns in every December 2025 release). Priced snapshots of {city}: "
                         f"{priced_snapshots(city)}")
    sample = listings[listings["in_sample"]].drop(columns="in_sample")
    features = build_features(sample, city).reset_index(drop=True)
    return listings.reset_index(drop=True), features


# ---------------------------------------------------------------------------------------------------------
# Optional helper for the model layer
# ---------------------------------------------------------------------------------------------------------
def impute_sizes(df: pd.DataFrame, train: pd.Series | None = None, by: str = "room_type",
                 cols: tuple[str, ...] = ("bedrooms", "beds", "baths")) -> pd.DataFrame:
    """Fill the size columns with the median per ``by`` group and add a ``<col>_missing`` flag.

    ``train`` is a boolean mask of the rows the medians may be computed from (all rows when None), so a
    cross-validation loop can pass its training fold and avoid peeking at the held-out rows. Returns a copy.
    """
    out = df.copy()
    train = pd.Series(True, index=out.index) if train is None else train.reindex(out.index).fillna(False)
    group = out[by] if by in out else pd.Series("all", index=out.index)
    for c in cols:
        if c not in out:
            continue
        miss = out[c].isna()
        by_group = out.loc[train].groupby(group[train])[c].median()
        fill = group.map(by_group).fillna(out.loc[train, c].median())
        out[c] = out[c].fillna(fill)
        out[f"{c}_missing"] = miss.astype(int)
    if {"guests_per_bedroom", "bedrooms", "accommodates"} <= set(out.columns):
        out["guests_per_bedroom"] = out["accommodates"] / out["bedrooms"].clip(lower=1)
    if {"guests_per_bed", "beds", "accommodates"} <= set(out.columns):
        out["guests_per_bed"] = out["accommodates"] / out["beds"].clip(lower=1)
    return out


# ---------------------------------------------------------------------------------------------------------
# Result object + cache
# ---------------------------------------------------------------------------------------------------------
class CityData:
    """What ``prepare`` returns: the typed listings, the standard features, and the other files, loaded lazily."""

    def __init__(self, city: str, snapshot: str, listings: pd.DataFrame, features: pd.DataFrame, meta: dict):
        self.city, self.snapshot = city, snapshot
        self.listings, self.features, self.meta = listings, features, meta
        self.folder = snapshot_dir(city, snapshot)

    @property
    def sample(self) -> pd.DataFrame:
        """The in-sample rows of ``listings``, in the same order as ``features``."""
        return self.listings[self.listings["in_sample"]].reset_index(drop=True)

    # the other Inside Airbnb files, one DataFrame each -------------------------------------------------
    @cached_property
    def reviews(self) -> pd.DataFrame:
        """(listing_id, date) of every review; ``in_sample`` marks reviews of in-sample listings."""
        r = load_reviews(self.city, self.snapshot)
        r["in_sample"] = r["listing_id"].isin(self.sample["id"])
        return r

    @cached_property
    def reviews_text(self) -> pd.DataFrame:
        """Full reviews with ``comments`` (100+ MB for the big cities)."""
        r = load_reviews(self.city, self.snapshot, with_text=True)
        r["in_sample"] = r["listing_id"].isin(self.sample["id"])
        return r

    @cached_property
    def calendar(self) -> pd.DataFrame:
        """365 days per listing: ``available``, min/max nights. Price columns are empty in every 2026 snapshot."""
        c = load_calendar(self.city, self.snapshot)
        return c.drop(columns=[col for col in ("price", "adjusted_price") if col in c and c[col].isna().all()])

    @cached_property
    def listings_summary(self) -> pd.DataFrame:
        return load_listings_summary(self.city, self.snapshot)

    @cached_property
    def neighbourhoods(self) -> pd.DataFrame:
        return load_neighbourhoods(self.city, self.snapshot)

    @cached_property
    def geojson(self) -> dict:
        return load_geojson(self.city, self.snapshot)

    def summary(self) -> str:
        m = self.meta
        return (f"{self.city} {self.snapshot} | listings {m['listings_rows']:,} rows, {m['sample_rows']:,} in sample | "
                f"features {m['features_cols']} cols | code {m['code_hash']} | data {m['fingerprint']}")

    def __repr__(self) -> str:
        return f"CityData({self.summary()})"


def _cache_dir(city: str, snapshot: str) -> Path:
    return PROCESSED_DIR / C.VERSION / f"{city}_{snapshot}"


def prepare(city: str, snapshot: str, *, cache: bool = True, strict: bool = True,
            verbose: bool = True) -> CityData:
    """Build (or load from cache) the frames of one city snapshot and print the fingerprint line.

    ``snapshot`` is required on purpose: there is no "latest". ``cache=False`` forces a rebuild;
    ``strict=False`` turns the sha256 and schema failures into warnings (for exploring other snapshots).
    """
    if snapshot not in list_snapshots(city):
        snapshot_dir(city, snapshot)  # raises with the download command
    folder = _cache_dir(city, snapshot)
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if (cache and meta_path.exists()) else None
    fresh = meta is None or meta.get("code_hash") != code_hash()

    if fresh:
        t0 = time.time()
        listings, features = build(city, snapshot, strict=strict)
        folder.mkdir(parents=True, exist_ok=True)
        _to_parquet(listings, folder / "listings.parquet")
        _to_parquet(features, folder / "features.parquet")
        listings = _read_parquet(folder / "listings.parquet")  # return exactly what is on disk
        features = _read_parquet(folder / "features.parquet")
        meta = {
            "city": city, "snapshot": snapshot, "version": C.VERSION, "code_hash": code_hash(),
            "built_at": pd.Timestamp.utcnow().isoformat(timespec="seconds"), "build_seconds": round(time.time() - t0, 1),
            "listings_rows": len(listings), "sample_rows": int(listings["in_sample"].sum()),
            "features_cols": features.shape[1],
            "fingerprint": fingerprint(listings), "features_fingerprint": fingerprint(features),
            "pandas": pd.__version__,
        }
        meta_path.write_text(json.dumps(meta, indent=1))
    else:
        listings = _read_parquet(folder / "listings.parquet")
        features = _read_parquet(folder / "features.parquet")

    data = CityData(city, snapshot, listings, features, meta)
    if verbose:
        print(data.summary() + ("" if fresh else "  (cached)"))
    return data


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (1, 2) or argv[0] in ("-h", "--help"):
        print("usage: python -m strfair.prep <city> [<snapshot>]   (snapshot defaults to the team's pinned one)")
        return 2
    city = argv[0]
    snapshot = argv[1] if len(argv) == 2 else C.PINNED_SNAPSHOTS.get(city)
    if snapshot is None:
        print(f"no pinned snapshot for {city!r}; pass one explicitly. Pinned: {C.PINNED_SNAPSHOTS}")
        return 2
    prepare(city, snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
