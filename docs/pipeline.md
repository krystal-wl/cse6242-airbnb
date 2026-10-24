# Data pipeline: how every notebook starts from the same data

*Rui Wang, 2026-10-23. Code: `strfair/config.py` (what the data is), `strfair/prep.py` (the steps).
Template: `notebooks/00_prepare_template.ipynb`.*

Each city is modelled on its own, from **one** snapshot. Before anyone models, the data goes through the
same preprocessing, so two teammates who name the same city and snapshot hold identical frames. The
notebook chooses *what* (city, snapshot); the package decides which bytes that is and which listings are
in the sample. Everything about modelling (features, split, imputation, encoders) is the notebook's own.

## 1. What a notebook does

```python
import strfair

CITY = "toronto"            # first cell: the only two choices the shared layer needs
SNAPSHOT = "2026-06-15"     # the team's dates are in the table below

data = strfair.prepare(CITY, SNAPSHOT)
# toronto 2026-06-15 | listings 22,198 rows, 18,262 in sample | features 106 cols | code 025a7a1b | data 597d7dbb
```

`snapshot` is required: there is no "latest". Inside Airbnb adds a snapshot every quarter, and a default
would silently move the data for whoever downloads after it appears.

| city            | team snapshot | stability check (March)                       |
| --------------- | ------------- | --------------------------------------------- |
| new-york-city   | 2026-06-14    | 2026-03-16                                    |
| los-angeles     | 2026-06-15    | 2026-03-16                                    |
| toronto         | 2026-06-15    | 2026-03-19 (partial scrape: per listing only) |
| san-diego       | 2026-06-27    | –                                             |
| clark-county-nv | 2026-06-27    | –                                             |
| jersey-city     | 2026-06-27    | –                                             |

Any other downloaded date also works, with a warning that the result will not match anyone else's.
September 2025 snapshots are refused by default (`strict=False` downgrades that to a warning): their
`price` is a different measure (`docs/features.md` §1.3).

## 2. What `prepare()` does, in order

| step | rule (all in `config.py`) | from |
| ---- | ------------------------- | ---- |
| verify the raw file | sha256 of `listings.csv.gz` must equal the recorded one | `download_data.py` manifest |
| load + type | dates, `t`/`f` booleans, `95%`, `$1,234.00` | `data.py` loaders (notebook 01) |
| schema check | the 2026 columns must exist | Isabelle's `column_checker` |
| mark the sample | `in_sample` = `price` present and in $10–$10,000, and `id`, `latitude`, `longitude`, `room_type`, `accommodates` present. Monthly quotes stay in | Isabelle's `needed_factors`; `docs/features.md` §1.2 |
| standard features | `build_features()` on the in-sample rows: the seven families of `features.py` plus amenities | `features.py`; kentxie's `amenities_breakout.py`; `docs/features_selection.md` |
| cache + fingerprint | parquet under `data/processed/v1/<city>_<snapshot>/`; the returned frames are read back from disk | – |

The cache is keyed by a hash of the package source, so pulling a change to `strfair/` rebuilds on the
next call. `prepare(..., cache=False)` forces it.

## 3. What you get: one DataFrame per Inside Airbnb file

| attribute               | contents | loaded |
| ----------------------- | -------- | ------ |
| `data.listings`         | every listing of the snapshot, typed, `in_sample` flag. **This is the contract.** | eagerly |
| `data.sample`           | the in-sample rows of `listings` | view |
| `data.features`         | the standard features for the sample rows, same order as `sample`. A starting point, not a contract | eagerly |
| `data.reviews`          | `listing_id`, `date` of every review, `in_sample` flag | on first access |
| `data.reviews_text`     | the same with `comments` (100+ MB for big cities) | on first access |
| `data.calendar`         | 365 days x listings: `available`, min/max nights (prices are empty in 2026) | on first access (11 M rows for NYC) |
| `data.listings_summary` | Inside Airbnb's compact listings file (maps) | on first access |
| `data.neighbourhoods`   | neighbourhood lookup | on first access |
| `data.geojson`          | neighbourhood polygons (dict) | on first access |

`data.meta` holds the fingerprint line's numbers and the build time.

## 4. What is deliberately *not* decided here

- **Features.** `data.features` is what `features.py` builds today (size, location, host, reviews, listing
  text, availability, amenities, quote timing). Use it, extend it, or build your own from `data.sample`.
  `strfair.feature_families(df)` says which builder a column came from. Size columns keep their `NaN`
  (`strfair.impute_sizes(df, train=mask)` fills them by room type and adds `_missing` flags); review scores
  are `NaN` for the ~22% of listings without a review (`no_reviews` / `no_rating` flag them).
- **Split / cross-validation.** None is pre-computed. Everyone holds the identical frame in the identical
  row order, so `KFold(5, shuffle=True, random_state=42)` already gives everyone the same folds; out-of-fold
  predictions give a residual for every listing, which the fair-price labels need anyway.
- **Which columns may be inputs.** Two reference lists, not enforcement: `strfair.LEAKY` (functions of the
  price: targets, `estimated_revenue_l365d`, `review_scores_value`, ...) and `strfair.DEMAND_RESPONSE`
  (availability, recent review velocity: for validating labels, per `docs/features.md` §2).
  `strfair.CATEGORICAL` names the categorical columns for encoders.
- **Target.** `price` / `log_price` plus two variants, `price_per_person` (Wang & Nicolau 2017) and
  `price_undiscounted` (quote before the length-of-stay discount), all in `features`.

## 5. Checking that two people have the same data

`prepare` prints one line. Compare the `data` hash: same string, same `listings`, byte for byte. The
`code` hash says which version of `strfair/` built it; if two people differ there, one has not pulled.

```
toronto 2026-06-15 | listings 22,198 rows, 18,262 in sample | features 106 cols | code 025a7a1b | data 597d7dbb
```

`python -m strfair.prep toronto` prints the same line from the shell.

## 6. Changing the preprocessing

Three kinds of change, from lightest to heaviest. Each family in `features.py` is one function
`df -> DataFrame` that returns new columns aligned on the input index; families do not depend on each
other, so you only need to read the one you touch.

**a. A feature for your own experiment: your notebook, no package change.**

```python
extra = pd.DataFrame({"long_stay": (data.sample["minimum_nights"] >= 28).astype(int)})
F = pd.concat([data.features, extra], axis=1)         # same row order as data.sample
```

**b. A feature everyone should get: one function in `features.py`, registered in `FAMILIES`.**

```python
def my_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    if "minimum_nights" in df:                          # skip columns a snapshot does not carry
        out["long_stay"] = (pd.to_numeric(df["minimum_nights"], errors="coerce") >= 28).astype(int)
    return out

FAMILIES["mine"] = my_features                          # at the bottom of features.py
```

Then rebuild (`prepare` notices the source change by itself) and open a PR. To change an existing
feature, edit its function; the amenity rules are in `strfair/amenities.py`. `build_features(df, city,
families=["size", "location"])` builds a subset if you want to try families one at a time.

**c. Which snapshot or which rows: `config.py`, `VERSION` bump, PR.** This changes the data everyone
holds, so it is a team decision. The file answers two questions only: which bytes (snapshot dates,
sha256, schema) and which rows (`in_sample`).

## 7. Where the teammates' code went

| contribution | where it lives now |
| ------------ | ------------------ |
| Isabelle: `drop_listings` / `needed_factors` | `config.REQUIRED_RAW_COLS` + the `in_sample` rule |
| Isabelle: `column_checker` | `config.SCHEMA_COLS` + the schema check |
| Isabelle: `dedupe_listings` / `load_all_cities` (pool all snapshots, keep the most complete row per id) | not used: one snapshot per city, ids are unique within a snapshot. Pooling 2026-03 and 2026-06 rows would mix quote dates (44% of NYC rows would come from March) |
| kentxie: `scripts/amenities_breakout.py` | `features.amenity_features` (`amg_*`, identical output, checked listing by listing on Jersey City); the script's three computed-then-dropped groups (paid parking, paid housekeeping, coffee) stay out |
| Krystal: Wi-Fi / free parking / smoking / breakfast flags | `am_wifi`, `am_free_parking`, `am_smoking_allowed`, `am_breakfast` (smoking and breakfast are rare: ~1–3% of listings) |
| Krystal: price per person per night (Wang & Nicolau target) | `price_per_person` in `features` |
| Krystal: no-review-count model, VIF, quantile regression, reviewed-only sample | the notebook's own (`no_reviews` is in `features` for the sample filter) |
| yseracloud: split, metrics, slices | the notebook's own; identical frames make a seeded `KFold` identical for everyone. Slice columns (`is_monthly_quote`, `room_type`) are in `features` |
