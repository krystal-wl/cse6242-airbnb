# Which raw columns can be model inputs

*Rui Wang, 2026-10-20. Evidence: `notebooks/02_raw_column_audit.ipynb`; the per-column table is
`docs/eda/raw_column_audit.csv`. Amenities are set aside for now (team decision); derived features come later.*

**Signal** = median over the six cities of Spearman |ρ| with log price (numeric / boolean columns) or √η²
(categorical columns: share of log-price variance explained by category means), on nightly quotes of the
latest priced snapshot. It ranks columns one at a time; it is not a model coefficient.

## 1. Four facts that decide what is usable

1. **Only 13 of the 25 downloaded snapshots carry a price** (`price_coverage.csv`): NYC and LA Mar + Jun
   2026; Toronto Sep 2025, Mar 2026 (partial scrape), Jun 2026; San Diego, Las Vegas, Jersey City Sep 2025 +
   Jun 2026. In those, 60–95% of listings are priced; the rest had no availability.
2. **`price` is the per-night rate of one dated quote**, and the quote's length is the listing's minimum
   stay (82–96% of listings). Where 30-night minimums dominate, so do monthly rates after a length-of-stay
   discount: 77% of NYC's priced listings, 54% Toronto, 46% LA, at roughly half the nightly level
   (`target_summary.csv`). Keep them, with the quote length as a control; clip prices to $10–$10,000.
3. **The Sep 2025 price is a different measure**: no quote date, and the same listings show a +17% to +51%
   median change by Jun 2026 with 62–82% moving more than 20% (`price_change_sep2025_jun2026.csv`). Model
   Sep 2025 releases separately; run the between-release stability test on Mar vs Jun 2026.
4. **Twelve columns are empty in every 2026 release** (`column_fill_rates.csv`), mostly host columns; the
   2026 schema adds `hosts_time_as_host_*` and the `price_quote_*` columns instead.

## 2. Verdict per column (92 raw columns)

**Target (2).** `price` (log, clipped); `price_quote_price_per_night` is identical to it in 2026.

**Use as is (15).**

| column | signal | note |
|---|---|---|
| `accommodates` | 0.70 | strongest single column |
| `room_type` | 0.48 | 4 levels; fold Hotel / Shared into Private for the interpretable model |
| `calculated_host_listings_count_private_rooms`, `_entire_homes` | 0.41, 0.31 | host portfolio mix (share of the host's listings) |
| `longitude`, `latitude` | 0.21, 0.16 | raw for the ensemble; distance to centre / spatial lag for the interpretable model |
| `host_listings_count`, `calculated_host_listings_count` | 0.20, 0.19 | log; ≥ 5 = multi-listing host |
| `number_of_reviews` | 0.15 | log; lifetime track record |
| `first_review`, `last_review` | 0.08, 0.07 | tenure in months; months since last review |
| `host_is_superhost` | 0.06 | weak, but readers expect it |
| `hosts_time_as_host_years`, `_months` | 0.05 | replaces `host_since` in 2026 |
| `bathrooms_text` | – | parse to a number plus a shared-bath flag; fills the gaps in `bathrooms` |

**Use with a caveat (9).**

| column | signal | caveat |
|---|---|---|
| `property_type` | 0.66 | ~70 levels (signal inflated by level count): group into hotel / apartment / house / other |
| `beds`, `bedrooms`, `bathrooms` | 0.64, 0.62, 0.53 | filled 74%, 80%, 73% in 2026: impute by room type and add a missing flag |
| `neighbourhood_cleansed` | 0.49 | 97–260 levels in the big cities (pool those with < 20 listings); only 6–7 levels in Las Vegas and Jersey City, where it carries almost no price information |
| `neighbourhood_group_cleansed` | 0.33 | NYC and LA only |
| `review_scores_location`, `review_scores_rating` | 0.24, 0.16 | 76% filled (no reviews): fill plus a missing flag |
| `license` | – | non-empty flag; city-specific. In NYC it decides whether a listing may quote nightly at all |

**Use as quote-timing controls (3).** `price_quote_checkin_date` → lead days (check-in minus scrape date);
`price_quote_checkout_date` → nights in the quote; `minimum_nights`. 2026 releases only for the first two.
These remove *when* and *for how long* the quote was taken so the residual is about the listing.

**Validation only, not inputs (10).** `availability_30/60/90/365/eoy`, `has_availability`,
`number_of_reviews_ltm`, `_l30d`, `_ly`, `reviews_per_month`. They are demand responses to the price (mixed
with host-blocked dates); the proposal uses them to check that under-priced listings show stronger demand.

**Do not use (13).**

| column(s) | reason |
|---|---|
| `estimated_revenue_l365d` | price × estimated occupancy: leakage (and the highest raw correlation with price after size) |
| `estimated_occupancy_l365d` | a formula of `number_of_reviews_ltm` and `minimum_nights`, no new information |
| `review_scores_value` | guests rate value *given* the price they paid: circular |
| `price_quote_total_price` | price × nights: a transform of the target |
| `host_since`, `host_response_time`, `host_response_rate`, `host_acceptance_rate`, `host_total_listings_count`, `instant_bookable`, `host_neighbourhood`, `neighbourhood`, `neighborhood_overview` | empty in every 2026 release (72–100% filled in Sep 2025; could be joined from there by `id` for the 51–75% of listings that existed then, not recommended for the baseline) |

**Later (5).** `name`, `description` (keyword flags / NLP), `host_about` (55% filled), `host_location`
(75%), `price_quote_raw` (JSON with the discount line items: the source of an undiscounted-price variant of
the target). **Set aside (1).** `amenities` (JSON list; needs parsing into flags).

**Optional, weak (16).** The other review sub-scores (`cleanliness`, `accuracy`, `checkin`,
`communication`: 0.11–0.13, 76% filled), the stay-rule variants (`maximum_nights`, `minimum_minimum_nights`,
`maximum_minimum_nights`, `minimum_maximum_nights`, `maximum_maximum_nights`, `*_nights_avg_ntm`: ≤ 0.16,
near-duplicates of `minimum_nights`), `calculated_host_listings_count_shared_rooms`, `host_has_profile_pic`,
`host_identity_verified`, `hosts_time_as_user_*` (≤ 0.06).

**Identifiers (16).** `id`, `host_id`, URLs, picture URLs, names, `scrape_id`, `last_scraped`, `source`,
`calendar_*`, `host_verifications`: keys and bookkeeping, not features.

## 3. The other raw source: review text

72–83% of listings have at least one review and 50–70% have five or more; comments run 150–270 characters
(`review_text_coverage.csv`). Enough for the proposal's one-city text experiment; it needs a missing
indicator for the 17–28% of listings without reviews.

## 4. Open decisions

- Target for monthly quotes: the quoted per-night rate (with the quote-length control) or the undiscounted
  rate from `price_quote_raw`. Notebook 03 reports error by quote type; a second run with the undiscounted
  rate is the next step.
- Review counts: lifetime `number_of_reviews` in, last-12-month velocity held out for validation. One model
  variant without any review count should confirm the labels do not depend on it.
- Las Vegas and Jersey City need a location feature beyond the neighbourhood file (distance to anchors or
  a leave-one-out spatial price lag).
