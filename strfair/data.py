"""Find and load Inside Airbnb snapshots stored under ``data/<city>/<YYYY-MM-DD>/``.

Everything here mirrors the helper cells of ``notebooks/01_load_city_starter.ipynb`` so that notebooks and
scripts can ``from strfair.data import load_listings`` instead of copying the cells. Two additions:

- ``priced_snapshots(city)`` / ``price_coverage()`` detect which snapshots actually carry a nightly price
  (Inside Airbnb left ``price`` empty in every December 2025 release and in several March 2026 ones).
- ``REPO_ROOT`` is derived from this file, so the loaders work from any working directory.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

#: The six cities the team chose (Boston was a download trial and is kept as an extra).
PROJECT_CITIES = ["new-york-city", "los-angeles", "toronto", "san-diego", "clark-county-nv", "jersey-city"]

#: Scrapes that missed a large share of listings (share of listings present in both the first and the last
#: snapshot that are absent from this one, measured 2026-09-29). Fine for per-listing work, not for counts.
PARTIAL_SNAPSHOTS: dict[str, dict[str, float]] = {
    "boston": {"2025-12-27": 0.17, "2026-03-28": 0.55},
    "toronto": {"2026-03-19": 0.28},
    "san-diego": {"2026-03-29": 0.10},
    "clark-county-nv": {"2026-03-28": 0.54},
    "jersey-city": {"2026-03-29": 0.51},
    # new-york-city and los-angeles: all snapshots complete
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LISTING_DATE_COLS = ["last_scraped", "calendar_last_scraped", "host_since", "first_review", "last_review",
                     "price_quote_checkin_date", "price_quote_checkout_date"]
LISTING_BOOL_COLS = ["host_is_superhost", "host_has_profile_pic", "host_identity_verified",
                     "has_availability", "instant_bookable"]
LISTING_PCT_COLS = ["host_response_rate", "host_acceptance_rate"]


# ---------------------------------------------------------------------------------------------------------
# Snapshot discovery
# ---------------------------------------------------------------------------------------------------------
def available_cities() -> list[str]:
    """City folders under data/ that contain at least one snapshot folder."""
    if not DATA_DIR.exists():
        return []
    return sorted(p.name for p in DATA_DIR.iterdir() if p.is_dir() and list_snapshots(p.name))


def list_snapshots(city: str) -> list[str]:
    """Snapshot dates downloaded for a city, oldest first."""
    city_dir = DATA_DIR / city
    if not city_dir.exists():
        return []
    return sorted(p.name for p in city_dir.iterdir() if p.is_dir() and DATE_RE.match(p.name))


def snapshot_dir(city: str, snapshot: str | None = None) -> Path:
    """Folder of one snapshot; latest when snapshot is None. Explains how to download if missing."""
    snaps = list_snapshots(city)
    if not snaps:
        raise FileNotFoundError(
            f"No data for '{city}' under {DATA_DIR}. Download it first (from the repo root):\n"
            f"    python scripts/download_data.py {city} --all-snapshots"
        )
    snapshot = snapshot or snaps[-1]
    if snapshot not in snaps:
        raise FileNotFoundError(f"'{city}' has no snapshot {snapshot}. Available: {snaps}")
    return DATA_DIR / city / snapshot


def is_partial(city: str, snapshot: str) -> bool:
    return snapshot in PARTIAL_SNAPSHOTS.get(city, {})


def data_inventory() -> pd.DataFrame:
    """One row per downloaded snapshot: file count, size, and whether the scrape is known to be partial."""
    rows = []
    for city in available_cities():
        for snap in list_snapshots(city):
            files = [p for p in (DATA_DIR / city / snap).iterdir() if p.is_file() and p.name != "manifest.json"]
            rows.append({
                "city": city, "snapshot": snap, "files": len(files),
                "size_mb": round(sum(p.stat().st_size for p in files) / 1e6, 1),
                "partial_scrape": is_partial(city, snap),
            })
    return pd.DataFrame(rows)


@lru_cache(maxsize=None)
def _price_stats(city: str, snapshot: str) -> tuple[int, int]:
    """(n_listings, n_priced) for one snapshot, reading only the price column."""
    path = DATA_DIR / city / snapshot / "listings.csv.gz"
    header = pd.read_csv(path, nrows=0).columns
    if "price" not in header:
        n = len(pd.read_csv(path, usecols=["id"]))
        return n, 0
    price = parse_price(pd.read_csv(path, usecols=["price"])["price"])
    return len(price), int(price.notna().sum())


def priced_snapshots(city: str, min_share: float = 0.05) -> list[str]:
    """Snapshots of a city whose listings file carries nightly prices for at least ``min_share`` of rows.

    Inside Airbnb shipped empty ``price`` columns in every December 2025 release and in the March 2026
    release of several cities; those snapshots are useless as modelling targets.
    """
    out = []
    for snap in list_snapshots(city):
        n, n_priced = _price_stats(city, snap)
        if n and n_priced / n >= min_share:
            out.append(snap)
    return out


def price_coverage(cities: list[str] | None = None) -> pd.DataFrame:
    """One row per city x snapshot: listings, priced listings, priced share, partial flag."""
    rows = []
    for city in cities or available_cities():
        for snap in list_snapshots(city):
            n, n_priced = _price_stats(city, snap)
            rows.append({"city": city, "snapshot": snap, "listings": n, "priced": n_priced,
                         "priced_share": round(n_priced / n, 3) if n else 0.0,
                         "partial_scrape": is_partial(city, snap)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------------------------------------
def parse_price(s: pd.Series) -> pd.Series:
    """'$1,234.00' -> 1234.0 (already-numeric columns pass through)."""
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    return pd.to_numeric(s.astype("string").str.replace(r"[$,]", "", regex=True), errors="coerce")


def _to_bool(s: pd.Series) -> pd.Series:
    return s.map({"t": True, "f": False}).astype("boolean")


def _to_fraction(s: pd.Series) -> pd.Series:
    """'95%' -> 0.95"""
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    return pd.to_numeric(s.astype("string").str.rstrip("%"), errors="coerce") / 100


def _tag(df: pd.DataFrame, city: str, folder: Path) -> pd.DataFrame:
    df.insert(0, "snapshot", folder.name)
    df.insert(0, "city", city)
    return df


def load_listings(city: str, snapshot: str | None = None, usecols: list[str] | None = None) -> pd.DataFrame:
    """Detailed listings (one row per listing, ~80-90 columns)."""
    folder = snapshot_dir(city, snapshot)
    df = pd.read_csv(folder / "listings.csv.gz", usecols=usecols, low_memory=False)
    for c in LISTING_DATE_COLS:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in LISTING_BOOL_COLS:
        if c in df:
            df[c] = _to_bool(df[c])
    for c in LISTING_PCT_COLS:
        if c in df:
            df[c] = _to_fraction(df[c])
    if "price" in df:
        df["price"] = parse_price(df["price"])
    return _tag(df, city, folder)


def load_listings_summary(city: str, snapshot: str | None = None) -> pd.DataFrame:
    """Compact listings table (id, name, host, neighbourhood, lat/lon, room_type, price, review counts)."""
    folder = snapshot_dir(city, snapshot)
    df = pd.read_csv(folder / "listings_summary.csv")
    df["last_review"] = pd.to_datetime(df["last_review"], errors="coerce")
    df["price"] = parse_price(df["price"])
    return _tag(df, city, folder)


def load_calendar(city: str, snapshot: str | None = None, listing_ids=None) -> pd.DataFrame:
    """365 days of availability per listing. Pass listing_ids to load a subset (streams in chunks)."""
    folder = snapshot_dir(city, snapshot)
    path = folder / "calendar.csv.gz"
    if listing_ids is None:
        df = pd.read_csv(path)
    else:
        keep = set(listing_ids)
        df = pd.concat(
            [chunk[chunk["listing_id"].isin(keep)] for chunk in pd.read_csv(path, chunksize=1_000_000)],
            ignore_index=True,
        )
    df["date"] = pd.to_datetime(df["date"])
    df["available"] = df["available"].eq("t")
    for c in ("price", "adjusted_price"):  # column exists before Dec 2025 but is empty in every snapshot we hold
        if c in df:
            df[c] = parse_price(df[c])
    return _tag(df, city, folder)


def load_reviews(city: str, snapshot: str | None = None, with_text: bool = False,
                 nrows: int | None = None) -> pd.DataFrame:
    """Reviews. with_text=False reads the small (listing_id, date) file; True reads the full comments.

    ``nrows`` caps the rows read (useful for a quick look at the text file, which is 100+ MB for big cities).
    """
    folder = snapshot_dir(city, snapshot)
    df = pd.read_csv(folder / ("reviews.csv.gz" if with_text else "reviews_summary.csv"), nrows=nrows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return _tag(df, city, folder)


def load_neighbourhoods(city: str, snapshot: str | None = None) -> pd.DataFrame:
    return pd.read_csv(snapshot_dir(city, snapshot) / "neighbourhoods.csv")


def load_geojson(city: str, snapshot: str | None = None) -> dict:
    with open(snapshot_dir(city, snapshot) / "neighbourhoods.geojson", encoding="utf-8") as f:
        return json.load(f)


def load_all_snapshots(city: str, loader=load_listings_summary, skip_partial: bool = False,
                       priced_only: bool = False, **kwargs) -> pd.DataFrame:
    """Concatenate one loader across every snapshot of a city (the 'snapshot' column tells them apart)."""
    snaps = list_snapshots(city)
    if priced_only:
        snaps = [s for s in snaps if s in set(priced_snapshots(city))]
    if skip_partial:
        snaps = [s for s in snaps if not is_partial(city, s)]
    return pd.concat([loader(city, s, **kwargs) for s in snaps], ignore_index=True)


def describe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """dtype, non-null share and an example value per column: the quickest way to see what a file holds."""
    rows = []
    for c in df.columns:
        s = df[c]
        non_null = s.notna()
        example = s[non_null].iloc[0] if non_null.any() else None
        rows.append({"column": c, "dtype": str(s.dtype), "non_null": f"{non_null.mean():.0%}",
                     "example": str(example)[:60]})
    return pd.DataFrame(rows)
