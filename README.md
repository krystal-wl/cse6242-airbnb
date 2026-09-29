# cse6242-airbnb

CSE 6242 (Data & Visual Analytics) group project on the
[Inside Airbnb](https://insideairbnb.com/get-the-data/) dataset.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

## Getting the data

Inside Airbnb scrapes each city roughly every quarter and keeps about the last
12 months of snapshots online for free (older data needs a request to them).
The datasets are **not committed** to this repo (they are large and `data/` is
git-ignored), so every teammate downloads them locally with
`scripts/download_data.py`.

```bash
# every city, with how many snapshots it has and the oldest/latest dates
python scripts/download_data.py --list

# every snapshot date of specific cities
python scripts/download_data.py --list boston new-york-city

# latest snapshot (all 7 files) of one or more cities
python scripts/download_data.py new-york-city boston chicago

# the whole archive of a city: every snapshot that is still online
python scripts/download_data.py boston --all-snapshots

# only snapshots on/after a date, only some files, and gunzip them
python scripts/download_data.py vaud --since 2026-01-01 --files listings calendar --extract

# one specific archived snapshot
python scripts/download_data.py boston@2026-03-28

# preview without downloading
python scripts/download_data.py paris --all-snapshots --dry-run
```

City names are matched loosely: `new-york-city`, `"New York City"` and
`new york city` all work, and accents are ignored (`sao-paulo` finds São Paulo;
its folder is the ASCII `data/sao-paulo/`). Unknown names print suggestions.
Existing files are skipped unless you pass `--force`, and an interrupted
download resumes where it stopped when you re-run the command.

### What a snapshot is

The date on a snapshot is the day Inside Airbnb scraped Airbnb for that city.
Relative to that day, the files cover different spans:

| file       | covers                                                   |
|------------|----------------------------------------------------------|
| listings   | the state of every listing on the scrape day             |
| calendar   | availability and price for the next 365 days             |
| reviews    | every review ever left (the only file with real history) |

Most cities have 4 quarterly snapshots online (e.g. Boston: 2025-09-23,
2025-12-27, 2026-03-28, 2026-06-15). New York City, Los Angeles and San
Francisco have 3; a few new cities have 1; Vaud and Edinburgh have multi-year
histories. `--list <city>` shows the exact dates.

### Where files go

Each snapshot gets its own folder, `data/<city-slug>/<YYYY-MM-DD>/`:

| `--files` key            | local file                | contents                                              |
|--------------------------|---------------------------|-------------------------------------------------------|
| `listings`               | `listings.csv.gz`         | one row per listing, ~75 columns (price, host, review scores, ...) |
| `calendar`               | `calendar.csv.gz`         | one row per listing per day for the next 365 days (availability, price) |
| `reviews`                | `reviews.csv.gz`          | one row per review with full comment text (largest file) |
| `listings-summary`       | `listings_summary.csv`    | compact listings table (good for quick plots/maps)    |
| `reviews-summary`        | `reviews_summary.csv`     | `listing_id`, `date` only (review counts over time)   |
| `neighbourhoods`         | `neighbourhoods.csv`      | neighbourhood / neighbourhood-group lookup            |
| `neighbourhoods-geojson` | `neighbourhoods.geojson`  | neighbourhood polygons for choropleth maps            |

A `manifest.json` in each snapshot folder records the source URL, size and
SHA-256 of every download, so we can confirm everyone has identical data.
Sizes vary a lot by city: one New York City snapshot is about 160 MB compressed
(reviews alone is ~120 MB), a small city like Albany is under 5 MB.

### Reading the data

Pandas reads the gzipped files directly, so `--extract` is only needed for
tools that want plain CSV (Tableau, D3, ...):

```python
from pathlib import Path
import pandas as pd

city = Path("data/boston")
latest = sorted(p for p in city.iterdir() if p.is_dir())[-1]   # ISO dates sort correctly
listings = pd.read_csv(latest / "listings.csv.gz")
calendar = pd.read_csv(latest / "calendar.csv.gz", parse_dates=["date"])

# stack all snapshots to compare quarters
frames = []
for snap in sorted(p for p in city.iterdir() if p.is_dir()):
    df = pd.read_csv(snap / "listings.csv.gz")
    df["snapshot_date"] = snap.name
    frames.append(df)
listings_all = pd.concat(frames, ignore_index=True)
```

## Notebooks

`notebooks/01_load_city_starter.ipynb` is the starting point for analysis. It
has loader functions for every file type (listings, calendar, reviews,
neighbourhoods, GeoJSON) that handle the quirks of the data: `$1,234.00`
price strings, `t`/`f` booleans, columns that were added or dropped between
snapshots, and the snapshots known to be partial scrapes. Set `CITY` at the
top and run it. Start Jupyter from the repo root so the notebook can find
`data/`:

```bash
jupyter lab
```

## Repo layout

```
cse6242-airbnb/
├── data/                       # downloaded datasets (git-ignored)
│   └── <city>/<YYYY-MM-DD>/    # one folder per snapshot
├── notebooks/
│   └── 01_load_city_starter.ipynb
├── scripts/
│   └── download_data.py        # Inside Airbnb downloader (see above)
├── requirements.txt
└── README.md
```
