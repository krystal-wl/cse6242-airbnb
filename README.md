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

| file     | covers                                                   |
| -------- | -------------------------------------------------------- |
| listings | the state of every listing on the scrape day             |
| calendar | availability and price for the next 365 days             |
| reviews  | every review ever left (the only file with real history) |

Most cities have 4 quarterly snapshots online (e.g. Boston: 2025-09-23,
2025-12-27, 2026-03-28, 2026-06-15). New York City, Los Angeles and San
Francisco have 3; a few new cities have 1; Vaud and Edinburgh have multi-year
histories. `--list <city>` shows the exact dates.

### Where files go

Each snapshot gets its own folder, `data/<city-slug>/<YYYY-MM-DD>/`:

| `--files` key            | local file               | contents                                                                |
| ------------------------ | ------------------------ | ----------------------------------------------------------------------- |
| `listings`               | `listings.csv.gz`        | one row per listing, ~75 columns (price, host, review scores, ...)      |
| `calendar`               | `calendar.csv.gz`        | one row per listing per day for the next 365 days (availability, price) |
| `reviews`                | `reviews.csv.gz`         | one row per review with full comment text (largest file)                |
| `listings-summary`       | `listings_summary.csv`   | compact listings table (good for quick plots/maps)                      |
| `reviews-summary`        | `reviews_summary.csv`    | `listing_id`, `date` only (review counts over time)                     |
| `neighbourhoods`         | `neighbourhoods.csv`     | neighbourhood / neighbourhood-group lookup                              |
| `neighbourhoods-geojson` | `neighbourhoods.geojson` | neighbourhood polygons for choropleth maps                              |

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

### Which snapshots have prices

Inside Airbnb left the `price` column empty in every December 2025 release
and in the March 2026 release of four cities, so only these snapshots can be
used as modelling targets (`strfair.data.priced_snapshots()` detects this from
the data; the full table is in `docs/eda/price_coverage.csv`):

| city            | priced snapshots                     |
| --------------- | ------------------------------------ |
| new-york-city   | 2026-03-16, 2026-06-14               |
| los-angeles     | 2026-03-16, 2026-06-15               |
| toronto         | 2025-09-11, 2026-03-19\*, 2026-06-15 |
| san-diego       | 2025-09-25, 2026-06-27               |
| clark-county-nv | 2025-09-23, 2026-06-27               |
| jersey-city     | 2025-09-25, 2026-06-27               |

\* partial scrape (28% of listings missing). Only the 2026 releases record the
check-in date behind each quote; the September 2025 price has no quote date.

## Shared package: `strfair/`

Loaders and feature builders that notebooks and scripts import instead of
copying cells (start Jupyter from the repo root, or add the root to
`sys.path` as notebooks 02 and 03 do):

```python
from strfair.data import load_listings, priced_snapshots, PROJECT_CITIES
from strfair.features import build_features

listings = load_listings("jersey-city", priced_snapshots("jersey-city")[-1])
features = build_features(listings)        # ~90 columns: target, quote timing, size, location,
                                           # host, reviews, listing text, availability
```

- `strfair/data.py`: snapshot discovery (`list_snapshots`, `priced_snapshots`,
  `PARTIAL_SNAPSHOTS`), loaders for every file type (same behaviour as the
  helper cells of notebook 01).
- `strfair/features.py`: one builder per feature family and `build_features()`
  to run them all. The `amenities` column is not used yet (team decision,
  Oct 2026); `CITY_CENTRES` is the reference table behind the
  distance-to-centre feature.

## Notebooks

| notebook                     | what it does                                                                                                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `01_load_city_starter.ipynb` | load one city, sanity-check it, plot a neighbourhood map                                                                                                                                                                 |
| `02_raw_column_audit.ipynb`  | every priced snapshot of the six cities: which raw columns are filled, what `price` measures, the signal of each column, and a use / caveat / do-not-use verdict per column. Saves its tables and figures to `docs/eda/` |

Start Jupyter from the repo root so the notebooks can find `data/`:

```bash
jupyter lab
```

## Docs

- [`docs/features.md`](docs/features.md): which raw columns can be model
  inputs, which cannot and why, and how the usable ones enter the models.
- [`docs/models.md`](docs/models.md): candidate interpretable and ensemble
  models, the evaluation protocol, and the recommendation.
- `docs/eda/`: the tables (CSV) and figures (PNG) behind both documents,
  produced by notebooks 02 and 03.

## Repo layout

```
cse6242-airbnb/
├── data/                       # downloaded datasets (git-ignored)
│   └── <city>/<YYYY-MM-DD>/    # one folder per snapshot
├── docs/
│   ├── features.md             # raw column audit: usable / not usable
│   ├── models.md               # candidate models + evaluation protocol
│   └── eda/                    # tables and figures from notebooks 02/03
├── notebooks/
│   ├── 01_load_city_starter.ipynb
│   ├── 02_raw_column_audit.ipynb
├── scripts/
│   └── download_data.py        # Inside Airbnb downloader (see above)
├── strfair/                    # shared package: loaders + feature builders
├── requirements.txt
└── README.md
```
