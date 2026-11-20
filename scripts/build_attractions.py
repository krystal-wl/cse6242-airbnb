"""Geocode the tourist attractions listed in ``scripts/tourist_area_distance.py`` into ``site/data/attractions.json``.

The map shows them as an optional overlay (docs/map_design.md §3). The list itself stays in Kent's script
(read here with ``ast``, so there is one copy); geocoding uses Nominatim at one request per second with a
project user agent, as its usage policy asks, so a full run takes about two minutes. Attractions that
Nominatim cannot find are reported and left out.

    python scripts/build_attractions.py
"""
from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "scripts" / "tourist_area_distance.py"
OUT = REPO_ROOT / "site" / "data" / "attractions.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "cse6242-strfair-map/0.1 (course project; Inside Airbnb price-fairness map)"}
CITY_SLUG = {
    "New York City": "new-york-city", "Toronto": "toronto", "Los Angeles": "los-angeles", "Boston": "boston",
    "San Diego": "san-diego", "Clark County, NV": "clark-county-nv",
}
QUERY_CITY = {"Clark County, NV": "Las Vegas, Nevada"}


def attractions_from_source() -> list[tuple[str, str]]:
    tree = ast.parse(SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "tourist_data" for t in node.targets):
            seen, out = set(), []
            for city, name in ast.literal_eval(node.value):
                if (city, name) not in seen:
                    seen.add((city, name))
                    out.append((city, name))
            return out
    raise SystemExit(f"tourist_data not found in {SRC}")


def geocode(query: str) -> tuple[float, float] | None:
    r = requests.get(NOMINATIM, params={"q": query, "format": "json", "limit": 1}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    hits = r.json()
    return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None


def main() -> None:
    items = attractions_from_source()
    features, missing = [], []
    for i, (city, name) in enumerate(items, 1):
        q = f"{name}, {QUERY_CITY.get(city, city)}"
        try:
            hit = geocode(q)
        except requests.RequestException as e:
            hit = None
            print(f"  {q}: {e}", file=sys.stderr)
        if hit:
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(hit[1], 5), round(hit[0], 5)]},
                             "properties": {"name": name, "city": CITY_SLUG.get(city, city)}})
        else:
            missing.append(q)
        print(f"[{i}/{len(items)}] {q}: {'ok' if hit else 'not found'}")
        time.sleep(1.1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"{len(features)} attractions -> {OUT}; not found: {missing or 'none'}")


if __name__ == "__main__":
    main()
