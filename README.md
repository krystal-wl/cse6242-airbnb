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

## Shared package: `strfair/` and the data pipeline

Every model notebook starts the same way: name a city and a snapshot, call
`prepare`, and get the same frames as everyone else
([`docs/pipeline.md`](docs/pipeline.md) has the details; copy
`notebooks/00_prepare_template.ipynb` to start a notebook). Everything after
that call (features, split, imputation, model) is the notebook's own.

```python
import strfair

CITY, SNAPSHOT = "toronto", "2026-06-15"     # the team's dates: strfair.PINNED_SNAPSHOTS
data = strfair.prepare(CITY, SNAPSHOT)
# toronto 2026-06-15 | listings 22,198 rows, 18,262 in sample | features 106 cols | code 025a7a1b | data 597d7dbb

data.listings                                # every listing, typed, with an in_sample flag (the contract)
data.sample                                  # the in-sample rows
data.features                                # standard features for those rows: a starting point, not a contract
data.reviews, data.calendar, data.neighbourhoods, data.geojson
```

Install the package once so `import strfair` works from any directory
(otherwise start Jupyter from the repo root):

```bash
pip install -e .
```

- `strfair/config.py`: what the data is: the pinned snapshot per city and its
  sha256, the schema, and which listings are in the sample. Nothing about
  modelling. Change a rule there, bump `VERSION`, open a PR.
- `strfair/prep.py`: `prepare()` verifies the raw file, types it, marks the
  sample, builds the standard features, caches parquet under
  `data/processed/<VERSION>/`, and prints a fingerprint so two people can
  confirm they hold the same data. `impute_sizes()` is an optional helper.
- `strfair/data.py`: snapshot discovery (`list_snapshots`, `priced_snapshots`,
  `PARTIAL_SNAPSHOTS`), loaders for every file type.
- `strfair/features.py`: one builder per feature family (`build_features()`
  runs them all), including the amenity family that absorbed
  `scripts/amenities_breakout.py`, plus the `LEAKY` / `DEMAND_RESPONSE`
  reference lists.
- `strfair/sentiment.py`: cleans review text, detects English-language reviews,
  computes VADER sentiment scores, and aggregates five listing-level
  sentiment features.
  
### Review Sentiment Analysis

The shared preprocessing pipeline includes VADER-based sentiment analysis of Airbnb guest reviews. Sentiment features are automatically generated when `strfair.prepare()` builds the dataset. No separate notebook is required.

**Setup and required data**

After pulling the latest code, install the updated dependencies:

```bash
python -m pip install -e .
```

The full review-text file (`reviews.csv.gz`) must be available locally for the selected city and snapshot. For example:

```bash
python scripts/download_data.py toronto@2026-06-15
```

**Usage**

```python
import strfair

data = strfair.prepare("toronto", "2026-06-15")
features = data.features

sentiment_cols = [
    "sentiment_review_count",
    "avg_sentiment",
    "sentiment_std",
    "negative_review_pct",
    "weighted_sentiment",
]

print(features[sentiment_cols].head())
```

**Generated sentiment features**

| Feature | Description |
|---|---|
| `sentiment_review_count` | Number of eligible reviews per listing |
| `avg_sentiment` | Average VADER compound sentiment score (-1 to +1) |
| `sentiment_std` | Standard deviation of sentiment scores; missing when fewer than 3 eligible reviews |
| `negative_review_pct` | Proportion of eligible reviews classified as negative |
| `weighted_sentiment` | Recency-weighted sentiment score (more weight is given to sentiment scores from reviews posted closer to the data snapshot date) |

**Review preprocessing**

- Removes missing, empty, and very short reviews (5 words or fewer).
- Keeps English-language reviews only.
- Excludes reviews dated after the snapshot date to prevent data leakage.
- Uses VADER to calculate sentiment scores and classify reviews as positive, neutral, or negative.
- Aggregates review sentiment at the listing level.

**Modeling considerations**

- Listings without eligible reviews are preserved with missing sentiment values.
- Handle missing sentiment values during model preprocessing rather than automatically dropping listings.
- Compare models with and without sentiment features to evaluate their predictive value.
- Sentiment processing may increase initial preparation time. Valid cached results can be reused when `cache=True`.

Implementation: `strfair/sentiment.py`, integrated through `strfair/prep.py`.

## Notebooks

| notebook                     | what it does                                                                                                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `00_prepare_template.ipynb`  | the two cells every model notebook starts with; copy it                                                                                                                                                                  |
| `01_load_city_starter.ipynb` | load one city, sanity-check it, plot a neighbourhood map                                                                                                                                                                 |
| `02_raw_column_audit.ipynb`  | every priced snapshot of the six cities: which raw columns are filled, what `price` measures, the signal of each column, and a use / caveat / do-not-use verdict per column. Saves its tables and figures to `docs/eda/` |

Start Jupyter from the repo root so the notebooks can find `data/`:

```bash
jupyter lab
```

## Interactive map (`site/`)

A static site over precomputed scores: no server, no modelling at request time
([`docs/map_design.md`](docs/map_design.md) is the design). It reads one scored
table per city from `data/scored/<city>_<snapshot>/scored.parquet`, the contract
the modelling notebooks produce. Until they do, a placeholder scorer fills it:

```bash
python scripts/stub_scores.py --all        # placeholder scores: ridge + random forest, out-of-fold (~3 min)
python scripts/build_map_data.py --all     # -> site/data/*.json (git-ignored, like data/)
python scripts/build_attractions.py        # optional overlay: geocodes Kent's attraction list (~2 min)
python -m http.server 8765 --directory site
```

Then open <http://localhost:8765>. One city at a time: points coloured by label,
filters (stay type defaults to nightly quotes), a listing card with the benchmark,
a dollar waterfall, comparables and the March-vs-June label where a city has two
priced releases, a compare basket, a neighbourhood layer, and a band slider. Paste
an Airbnb listing URL or id in the search box to jump to it. The map reads only
the scored table, so swapping the stub for the real models is a rebuild, not a
code change.

## Docs

- [`docs/pipeline.md`](docs/pipeline.md): the preprocessing every notebook
  shares: steps, the frames you get, column roles, how to check two people
  hold the same data.
- [`docs/features.md`](docs/features.md): which raw columns can be model
  inputs, which cannot and why, and how the usable ones enter the models.
- [`docs/features_selection.md`](docs/features_selection.md): the column
  choices checked against Wang & Nicolau (2017).
- [`docs/models.md`](docs/models.md): candidate interpretable and ensemble
  models, the evaluation protocol, and the recommendation.
- [`docs/map_design.md`](docs/map_design.md): the interactive map: what it
  shows, the fixed feature set, the scored-table contract it reads, stack, plan.
- `docs/eda/`: the tables (CSV) and figures (PNG) behind the documents,
  produced by notebook 02.

## Repo layout

```
cse6242-airbnb/
├── data/                       # git-ignored
│   ├── <city>/<YYYY-MM-DD>/    # downloaded snapshots, one folder each
│   └── processed/<version>/    # parquet cache written by strfair.prepare()
├── docs/
│   ├── pipeline.md             # the shared preprocessing: steps, frames, roles
│   ├── features.md             # raw column audit: usable / not usable
│   ├── features_selection.md   # column choices vs Wang & Nicolau (2017)
│   ├── models.md               # candidate models + evaluation protocol
│   ├── map_design.md           # the interactive map: scope, data contract, stack
│   └── eda/                    # tables and figures from notebook 02
├── notebooks/
│   ├── 00_prepare_template.ipynb
│   ├── 01_load_city_starter.ipynb
│   └── 02_raw_column_audit.ipynb
├── scripts/
│   ├── download_data.py        # Inside Airbnb downloader (see above)
│   ├── amenities_breakout.py   # absorbed into strfair.features.amenity_features
│   ├── tourist_area_distance.py # Kent's attraction list + distance feature
│   ├── stub_scores.py          # placeholder scored table until the models exist
│   ├── build_map_data.py       # scored table -> site/data/ (the map's files)
│   └── build_attractions.py    # attraction overlay (geocodes the list above)
├── site/                       # the interactive map: static HTML + ES modules
│   ├── index.html, styles.css
│   ├── app/                    # main, mapview, filters, card, compare, hoods, charts
│   └── data/                   # git-ignored, written by build_map_data.py
├── strfair/                    # shared package
│   ├── config.py               # what the data is: snapshots, sha256, schema, sample rule
│   ├── prep.py                 # prepare(): verify, type, mark the sample, standard features
│   ├── data.py                 # snapshot discovery + loaders
│   ├── features.py             # feature families; how to add one is in its docstring
│   └── amenities.py            # the amenity family (kentxie's groups + the four flags)
│   └── sentiment.py.           # sentiment features
├── pyproject.toml              # pip install -e .
├── requirements.txt
└── README.md
```
