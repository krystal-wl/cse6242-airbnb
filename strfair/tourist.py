"""Distance to the nearest listed tourist attraction (per city).

Coordinates are fixed in-repo (no live geocoding) so ``prepare`` stays offline and
reproducible. Jersey City uses local anchors plus core NYC attractions. Derived from
``scripts/tourist_area_distance.py`` attraction lists.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

# (name, lat, lon). Approximate public locations; good enough for nearest-km features.
ATTRACTIONS: dict[str, list[tuple[str, float, float]]] = {
    "new-york-city": [
        ("Times Square", 40.7580, -73.9855),
        ("Central Park", 40.7829, -73.9654),
        ("Statue of Liberty", 40.6892, -74.0445),
        ("Empire State Building", 40.7484, -73.9857),
        ("Rockefeller Center", 40.7587, -73.9787),
        ("Brooklyn Bridge", 40.7061, -73.9969),
        ("The Metropolitan Museum of Art", 40.7794, -73.9632),
        ("High Line", 40.7480, -74.0048),
        ("One World Trade Center", 40.7127, -74.0134),
        ("Grand Central Terminal", 40.7527, -73.9772),
        ("Chelsea Market", 40.7424, -74.0061),
        ("Madison Square Garden", 40.7505, -73.9934),
        ("SoHo", 40.7233, -74.0030),
        ("Chinatown", 40.7158, -73.9970),
        ("Williamsburg", 40.7081, -73.9571),
        ("DUMBO", 40.7033, -73.9882),
        ("West Village", 40.7336, -74.0027),
    ],
    "toronto": [
        ("CN Tower", 43.6426, -79.3871),
        ("Royal Ontario Museum", 43.6677, -79.3948),
        ("Distillery District", 43.6503, -79.3596),
        ("St. Lawrence Market", 43.6487, -79.3715),
        ("Casa Loma", 43.6780, -79.4094),
        ("Ripley's Aquarium of Canada", 43.6424, -79.3860),
        ("Toronto Islands", 43.6205, -79.3782),
        ("High Park", 43.6465, -79.4637),
        ("Art Gallery of Ontario", 43.6536, -79.3925),
        ("Eaton Centre", 43.6544, -79.3807),
        ("Yorkville", 43.6706, -79.3936),
        ("Kensington Market", 43.6546, -79.4005),
        ("Financial District", 43.6486, -79.3817),
    ],
    "los-angeles": [
        ("Hollywood Sign", 34.1341, -118.3215),
        ("Griffith Observatory", 34.1184, -118.3004),
        ("Universal Studios Hollywood", 34.1381, -118.3534),
        ("Santa Monica Pier", 34.0094, -118.4973),
        ("Venice Beach", 33.9850, -118.4695),
        ("The Getty Center", 34.0780, -118.4741),
        ("Walk of Fame", 34.1016, -118.3267),
        ("The Grove", 34.0722, -118.3574),
        ("Los Angeles County Museum of Art", 34.0639, -118.3592),
        ("Downtown Los Angeles", 34.0407, -118.2468),
        ("Crypto.com Arena", 34.0430, -118.2673),
        ("Dodger Stadium", 34.0739, -118.2400),
        ("TCL Chinese Theatre", 34.1020, -118.3410),
        ("Little Tokyo", 34.0500, -118.2395),
        ("Malibu", 34.0259, -118.7798),
        ("Echo Park", 34.0782, -118.2606),
        ("Koreatown", 34.0610, -118.3026),
        ("Beverly Hills", 34.0736, -118.4004),
    ],
    "san-diego": [
        ("Balboa Park", 32.7341, -117.1446),
        ("San Diego Zoo", 32.7353, -117.1490),
        ("USS Midway Museum", 32.7137, -117.1751),
        ("Gaslamp Quarter", 32.7110, -117.1605),
        ("La Jolla Cove", 32.8500, -117.2728),
        ("Old Town San Diego", 32.7549, -117.1970),
        ("Coronado Beach", 32.6859, -117.1835),
        ("Seaport Village", 32.7089, -117.1700),
        ("Cabrillo National Monument", 32.6725, -117.2425),
        ("Little Italy", 32.7233, -117.1683),
        ("Petco Park", 32.7073, -117.1566),
        ("Pacific Beach", 32.7948, -117.2540),
        ("Ocean Beach", 32.7493, -117.2470),
        ("Point Loma", 32.6700, -117.2410),
        ("SeaWorld San Diego", 32.7645, -117.2263),
    ],
    "clark-county-nv": [
        ("The Las Vegas Strip", 36.1147, -115.1728),
        ("Fremont Street Experience", 36.1699, -115.1435),
        ("Red Rock Canyon", 36.1352, -115.4270),
        ("The High Roller", 36.1174, -115.1682),
        ("Bellagio Conservatory", 36.1126, -115.1767),
        ("The Sphere", 36.1206, -115.1619),
        ("Hoover Dam", 36.0163, -114.7377),
        ("Neon Museum", 36.1770, -115.1360),
        ("Mandalay Bay", 36.0919, -115.1750),
        ("Seven Magic Mountains", 35.8384, -115.2700),
        ("Strat Hotel", 36.1475, -115.1560),
    ],
    # Local anchors + core NYC (JC listings often priced vs Manhattan access).
    "jersey-city": [
        ("Exchange Place", 40.7165, -74.0330),
        ("Liberty State Park", 40.7040, -74.0500),
        ("Newport Jersey City", 40.7260, -74.0340),
        ("Journal Square", 40.7320, -74.0630),
        ("Times Square", 40.7580, -73.9855),
        ("World Trade Center", 40.7127, -74.0134),
        ("Statue of Liberty", 40.6892, -74.0445),
        ("Brooklyn Bridge", 40.7061, -73.9969),
    ],
}

_EARTH_KM = 6371.0


def tourist_features(df: pd.DataFrame, city: str | None = None) -> pd.DataFrame:
    """``dist_to_nearest_attraction_km`` and ``log_dist_to_nearest_attraction``."""
    out = pd.DataFrame(index=df.index)
    city = city or (df["city"].iloc[0] if "city" in df and len(df) else None)
    if city not in ATTRACTIONS or "latitude" not in df or "longitude" not in df:
        return out

    attrs = ATTRACTIONS[city]
    attr_coords = np.radians(np.array([[a[1], a[2]] for a in attrs], dtype=float))
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    ok = lat.notna() & lon.notna()
    dist = pd.Series(np.nan, index=df.index, dtype=float)
    if ok.any():
        tree = BallTree(attr_coords, metric="haversine")
        listing = np.radians(np.column_stack([lat[ok].to_numpy(), lon[ok].to_numpy()]))
        d_rad, _ = tree.query(listing, k=1)
        dist.loc[ok] = d_rad.flatten() * _EARTH_KM

    out["dist_to_nearest_attraction_km"] = dist
    out["log_dist_to_nearest_attraction"] = np.log1p(dist)
    return out
