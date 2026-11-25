"""Turn a scored table into the files the map reads (docs/map_design.md §5).

    python scripts/build_map_data.py --all                      # six cities: September 2026, June as previous release
    python scripts/build_map_data.py san-diego                  # one city, same two releases
    python scripts/build_map_data.py new-york-city 2026-06-14 --prev 2026-03-16   # any other pair of scored releases

The dates come from ``RELEASES`` in ``scripts/score_listings.py``: September is what the map shows (the
release the results are reported on), June is the previous release for the between-release view.

Reads ``data/scored/<city>_<snapshot>/scored.parquet`` (the contract written by ``scripts/build_scored.py``,
or by the placeholder ``scripts/stub_scores.py``) and writes under ``site/data/``:

    <city>_<snapshot>.json              the scored table, column-oriented, one array per column
    <city>_<snapshot>.metrics.json      listings, error per model, label shares, model agreement, release stability
    <city>.neighbourhoods.geojson       Inside Airbnb polygons, copied from the snapshot folder
    cities.json                         the list of cities the site offers (merged with what is already there)

Listing ids are written as strings: Airbnb ids exceed 2^53 and lose digits as JavaScript numbers.
Labels are not written: the map computes them from the ratios and the band the reader chooses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import strfair  # noqa: E402
from score_listings import RELEASES  # noqa: E402
from strfair.features import CITY_CENTRES  # noqa: E402

SCORED_DIR = REPO_ROOT / "data" / "scored"
SITE_DATA = REPO_ROOT / "site" / "data"
DEFAULT_BAND = 0.20

CITY_NAMES = {
    "new-york-city": "New York City", "los-angeles": "Los Angeles", "toronto": "Toronto",
    "san-diego": "San Diego", "clark-county-nv": "Las Vegas (Clark County)", "jersey-city": "Jersey City",
    "boston": "Boston",
}

#: column -> (json name, rounding or None). Order is the order in the file.
COLUMNS = [
    ("id", "id", None), ("name", "name", None), ("latitude", "lat", 5), ("longitude", "lon", 5),
    ("neighbourhood_cleansed", "hood", None), ("room_type", "room", None), ("property_group", "prop", None),
    ("accommodates", "guests", 0), ("bedrooms", "bedrooms", 0), ("baths", "baths", 1),
    ("review_scores_rating", "rating", 2), ("number_of_reviews", "reviews", 0), ("superhost", "superhost", 0),
    ("km_to_centre", "km", 2), ("n_amenities", "amenities", 0),
    ("price", "price", 0), ("price_quote_checkin_date", "checkin", None), ("quote_nights", "nights", 0),
    ("lead_days", "lead", 0), ("is_monthly_quote", "monthly", 0),
    ("fair_interp", "fair_i", 0), ("fair_ens", "fair_e", 0), ("ratio_interp", "r_i", 3), ("ratio_ens", "r_e", 3),
    ("ratio_interp_prev", "r_i_prev", 3), ("ratio_ens_prev", "r_e_prev", 3),
    ("price_prev", "price_prev", 0), ("fair_interp_prev", "fair_i_prev", 0),
]


def labels(ratio: pd.Series, band: float) -> pd.Series:
    return pd.Series(np.where(ratio < 1 - band, "under", np.where(ratio > 1 + band, "over", "fair")), index=ratio.index)


def _col(series: pd.Series, nd: int | None) -> list:
    if nd is None:
        return [None if pd.isna(v) else v for v in series.tolist()]
    vals = pd.to_numeric(series, errors="coerce")
    out = []
    for v in vals.tolist():
        if v is None or pd.isna(v):
            out.append(None)
        elif nd == 0:
            out.append(int(round(v)))
        else:
            out.append(round(float(v), nd))
    return out


def load_scored(city: str, snapshot: str) -> pd.DataFrame:
    path = SCORED_DIR / f"{city}_{snapshot}" / "scored.parquet"
    if not path.exists():
        raise SystemExit(f"no scored table at {path}; run scripts/build_scored.py for this release (or scripts/stub_scores.py {city} {snapshot})")
    df = pd.read_parquet(path)
    df["id"] = df["id"].astype(str)
    return df


def metrics(df: pd.DataFrame, prev: pd.DataFrame | None, band: float) -> dict:
    out = {"n": int(len(df)), "band": band, "median_price": float(df["price"].median()),
           "base_price": {k: (float(df.loc[df["is_monthly_quote"] == v, "base_price"].iloc[0]) if (df["is_monthly_quote"] == v).any() else None)
                          for k, v in (("nightly", 0), ("monthly", 1))} if "base_price" in df else None,
           "monthly_share": float(df["is_monthly_quote"].mean()), "models": {}}
    li, le = labels(df["ratio_interp"], band), labels(df["ratio_ens"], band)
    for key, fair, lab in (("interp", "fair_interp", li), ("ens", "fair_ens", le)):
        err = df["price"] - df[fair]
        out["models"][key] = {
            "mae_usd": float(err.abs().mean()), "median_abs_err_usd": float(err.abs().median()),
            "median_abs_pct_err": float((err.abs() / df["price"]).median()),
            "label_share": lab.value_counts(normalize=True).round(4).to_dict(),
        }
    out["agreement_share"] = float((li == le).mean())
    nightly = df["is_monthly_quote"] == 0
    out["nightly"] = {"n": int(nightly.sum()),
                      "median_abs_err_usd": float((df.loc[nightly, "price"] - df.loc[nightly, "fair_interp"]).abs().median())}
    if prev is not None:
        both = df.merge(prev[["id", "ratio_interp"]].rename(columns={"ratio_interp": "ratio_prev"}), on="id")
        lp = labels(both["ratio_prev"], band)
        lc = labels(both["ratio_interp"], band)
        out["previous"] = {"snapshot": str(prev["snapshot"].iloc[0]), "n_both": int(len(both)),
                           "kept_label_share": float((lp == lc).mean()) if len(both) else None,
                           "flipped_extreme_share": float((((lp == "under") & (lc == "over")) | ((lp == "over") & (lc == "under"))).mean()) if len(both) else None}
    return out


def build(city: str, snapshot: str, prev_snapshot: str | None, band: float) -> None:
    df = load_scored(city, snapshot)
    prev = None
    if prev_snapshot:
        try:
            prev = load_scored(city, prev_snapshot)
        except SystemExit as e:
            print(f"  previous release skipped: {e}")
    if prev is not None:
        p = prev[["id", "ratio_interp", "ratio_ens", "price", "fair_interp"]].rename(columns={
            "ratio_interp": "ratio_interp_prev", "ratio_ens": "ratio_ens_prev", "price": "price_prev", "fair_interp": "fair_interp_prev"})
        df = df.merge(p, on="id", how="left")
    else:
        for c in ("ratio_interp_prev", "ratio_ens_prev", "price_prev", "fair_interp_prev"):
            df[c] = np.nan

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    columns = {}
    for src, name, nd in COLUMNS:
        if src in df:
            columns[name] = _col(df[src], nd)
    columns["contrib"] = [json.loads(s) if isinstance(s, str) else [] for s in df["contributions"]]
    columns["comps"] = [json.loads(s) if isinstance(s, str) else [] for s in df["comps"]]
    columns["comps"] = [[str(c) for c in cs] for cs in columns["comps"]]
    stem = f"{city}_{snapshot}"
    payload = {"city": city, "snapshot": snapshot, "prev_snapshot": prev_snapshot if prev is not None else None,
               "n": int(len(df)), "stub": _is_stub(city, snapshot), "columns": columns}
    (SITE_DATA / f"{stem}.json").write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
    (SITE_DATA / f"{stem}.metrics.json").write_text(json.dumps(metrics(df, prev, band), indent=1))

    geo = strfair.load_geojson(city, snapshot)
    (SITE_DATA / f"{city}.neighbourhoods.geojson").write_text(json.dumps(geo, separators=(",", ":")))

    lat0, lon0 = CITY_CENTRES.get(city, (float(df["latitude"].median()), float(df["longitude"].median())))
    entry = {
        "slug": city, "name": CITY_NAMES.get(city, city), "snapshot": snapshot,
        "prev_snapshot": prev_snapshot if prev is not None else None,
        "center": [round(lon0, 5), round(lat0, 5)],
        "bounds": [round(float(df["longitude"].quantile(0.01)), 4), round(float(df["latitude"].quantile(0.01)), 4),
                   round(float(df["longitude"].quantile(0.99)), 4), round(float(df["latitude"].quantile(0.99)), 4)],
        "n": int(len(df)), "stub": payload["stub"],
        "files": {"listings": f"{stem}.json", "metrics": f"{stem}.metrics.json", "geojson": f"{city}.neighbourhoods.geojson"},
    }
    cities_path = SITE_DATA / "cities.json"
    cities = json.loads(cities_path.read_text()) if cities_path.exists() else []
    cities = [c for c in cities if c["slug"] != city] + [entry]
    order = list(strfair.PINNED_SNAPSHOTS)
    cities.sort(key=lambda c: order.index(c["slug"]) if c["slug"] in order else 99)
    cities_path.write_text(json.dumps(cities, indent=1))
    size = (SITE_DATA / f"{stem}.json").stat().st_size / 1e6
    print(f"{city} {snapshot} | {len(df):,} listings | previous: {entry['prev_snapshot']} | {size:.1f} MB -> site/data/{stem}.json")


def _is_stub(city: str, snapshot: str) -> bool:
    meta = SCORED_DIR / f"{city}_{snapshot}" / "meta.json"
    return bool(json.loads(meta.read_text()).get("stub")) if meta.exists() else False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("city", nargs="?")
    ap.add_argument("snapshot", nargs="?")
    ap.add_argument("--prev", help="earlier priced release for the between-release view (default: the city's June release)")
    ap.add_argument("--band", type=float, default=DEFAULT_BAND, help="fair band for the metrics file (the map has its own slider)")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    current, previous = RELEASES["september"], RELEASES["june"]
    if args.all:
        jobs = [(c, s, previous.get(c)) for c, s in current.items()]
    elif args.city:
        snap = args.snapshot or current[args.city]
        prev = args.prev or previous.get(args.city)
        jobs = [(args.city, snap, prev if prev != snap else None)]  # a release is never its own previous one
    else:
        ap.error("give a city or --all")
    for city, snap, prev in jobs:
        build(city, snap, prev, args.band)


if __name__ == "__main__":
    main()
