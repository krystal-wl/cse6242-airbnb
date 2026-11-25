# Interactive map: scope and design

*Rui Wang, 2026-10-31. Design for the visualization track (Rui, Wanzhen, Kent). Companion to `docs/pipeline.md`
(the data) and `docs/models.md` (the scores the map shows). Status: built in `site/` on 2026-10-31 over
placeholder scores (`scripts/stub_scores.py`); §5 is the contract the modelling notebooks fill. The README
says how to run it.*

*Update 2026-11-23: the map shows the **September 2026** release of all six cities, the release the results
are reported on, with **June 2026** as the previous release (June was used for tuning). March 2026 is
dropped: only three cities have prices in it. The real scores come from `scripts/build_scored.py`. The
listing counts in §1 and the plan in §7 are the original June figures and dates.*

The proposal defines the map in one sentence: for any listing a traveler is looking at, what would a
comparable place in this part of the city typically cost per night for similar dates, and is this listing
cheaper, about the same, or more expensive than that? The answer has three parts, and every screen of the map
exists to show them: a **benchmark nightly price**, a **label** (underpriced / fair / overpriced), and a short
**explanation in dollars** of what accounts for the gap. The map is a tool for checking one listing, not a
price heat map.

Four commitments in the proposal's engineering text constrain the design:

1. Every score is **precomputed**; the map is a **static site over a small data file** with no server-side
   modelling (GitHub Pages).
2. The **feature set is fixed** at the proposal stage, so the map cannot absorb unbounded effort. §3 is that
   fixed set.
3. A confident label is shown only when the price sits outside the band under **every model variant**, and
   the data's limitations are **stated in the interface itself**.
4. The final check requires the map deployed **with the between-release view** (June vs September 2026, all six
   cities).

The user test (decision speed, picking the better-value option with vs without the tool, inaction rate) adds
a fifth: the map must support *choosing between a few candidate listings*, not only reading one.

## 1. One city at a time

Cities are modelled separately and never pooled (`docs/pipeline.md`), so the map shows one city at a time
from its September 2026 snapshot (`RELEASES` in `scripts/score_listings.py`) and the user switches city
explicitly.
Nothing on the map compares across cities. Listing counts set the performance budget:

| city            | snapshot   | in-sample listings | monthly (28+ night) quotes |
| --------------- | ---------- | -----------------: | -------------------------: |
| new-york-city   | 2026-06-14 |             21,500 |                        77% |
| los-angeles     | 2026-06-15 |             38,145 |                        46% |
| toronto         | 2026-06-15 |             18,262 |                        54% |
| san-diego       | 2026-06-27 |             11,850 |                        low |
| clark-county-nv | 2026-06-27 |             17,250 |                        low |
| jersey-city     | 2026-06-27 |              2,100 |                        low |

September 2025 releases are never shown: their `price` is a different measure (`docs/features.md` §1.3).

## 2. Three layers

**2.1 Explore (the map).** All in-sample listings of the city as points, coloured by label. A search box at
the top accepts an Airbnb URL or listing id and flies to that listing with its card open: travelers and hosts
arrive holding a listing, so this is the primary entry, not clicking around. A filter panel on the left, a
city metrics strip at the bottom, and a persistent "how to read this" caveat panel.

**2.2 Listing card.** Opens on click or search. Top to bottom:

| block | content |
| ----- | ------- |
| verdict | quoted price and benchmark side by side; the gap in dollars and in percent; the label; whether the interpretable and ensemble models agree (confident) or not |
| quote context | one line: "This quote was for N nights from <check-in date>, captured D days ahead." Monthly quotes say so explicitly. Makes it visible that this is one dated quote, not a rate card |
| why | a small waterfall from the city median to this listing's benchmark: the 5 largest contributions in dollars (e.g. kitchen +$31, private room −$57, 1.2 km further from centre −$4), then "everything else" |
| the listing | room type, guests, bedrooms, baths, rating, review count, superhost; a link to the listing on Airbnb |
| comparables | the 5 most similar listings (same room type, bedrooms ±1, within 1 km, nightly or monthly to match): their price, benchmark and ratio, each clickable. "Relative to similar places" has to be visible, not only a model number |
| between releases | for listings priced in June 2026 too: the June label and whether it agrees |
| pin | adds the listing to the compare basket |

**2.3 Compare basket.** Up to 5 pinned listings side by side: price, benchmark, ratio, label, confidence,
guests, bedrooms, rating, distance to centre. This is the screen the user test exercises.

## 3. Feature list

**Must have (progress-report prototype, one city):**

| feature | why |
| ------- | --- |
| city switcher, pinned snapshot | §1 |
| search by Airbnb URL / id | the proposal's use case; the user-test entry point |
| points coloured by label | the one encoding that answers the question at a glance |
| **stay-type filter, default nightly** | 77% of NYC's priced listings are 28+ night quotes at about half the nightly level. Shown together, every "bargain" is a monthly rate. The single most important control on the map |
| filters: room type, guests ≥ n, bedrooms, price range, label, confident only | narrows to the traveler's own search |
| listing card (verdict, quote context, why, the listing, Airbnb link) | the three outputs of the proposal |
| comparables on the card | makes "relative to similar places" concrete |
| caveat panel, always visible | commitment 3 |
| city metrics strip: listings, held-out MAE in dollars, share fair | tells the reader how much to trust the city's benchmark |

**Should have (final):**

| feature | why |
| ------- | --- |
| compare basket | the user test |
| neighbourhood layer: choropleth of median ratio / share over / share under, click for the ratio histogram (the clicked neighbourhood is outlined while its popup is open) | the neighbourhood-level view promised to researchers and hosts (proposal Q4) |
| between-release toggle (June 2026), plus the card line and a "kept their label" share in the metrics strip | commitment 4 |
| band-width slider (default ±20%) | labels are computed client-side from the ratio, so the slider turns the sensitivity analysis into an interaction at almost no cost |
| tourist-attraction overlay | Kent's anchor points (`scripts/tourist_area_distance.py`) as context; pairs with the distance feature |

**Not in scope:**

| feature | why not |
| ------- | ------- |
| date picker / "what would it cost on another date" | the data holds one quote per listing; the proposal says this cannot be recovered. Showing it would be a lie |
| what-if calculator (add a kitchen, see the price) | the proposal's own risk: hosts gaming the model; and the feature set is frozen |
| cross-city comparison, accounts, any server | commitments 1 and 2 |
| live Airbnb prices or photos | not in the data. `picture_url` exists and could be hot-linked, but it depends on Airbnb's CDN; optional, decide late |

## 4. Design rules

- **Colour.** Three categorical colours for the label: blue (under), grey (fair), orange (over). Not red and
  green. The ratio is also available as a continuous diverging scale for the neighbourhood layer.
- **Label.** `label = under if ratio < 1 − band, over if ratio > 1 + band, else fair`, with `ratio =
  price / benchmark` and `band = 0.20` by default (the Albany pilot's value). Computed in the browser from
  the shipped ratios so the band slider needs no rebuild.
- **Confident.** Both models give the same label and the price sits outside the band under both. Points with
  a non-confident under/over label are drawn with a lighter fill; the card says "the two models disagree".
- **Comparables.** Same `room_type`, `bedrooms` within ±1, same stay type (nightly / monthly), nearest 5 by
  distance within 1 km, widened to 3 km if fewer than 5. Precomputed per listing, not searched in the browser.
- **Quote context.** `lead_days`, `quote_nights`, `price_quote_checkin_date` are shown on every card. The
  benchmark already controls for them (`docs/models.md`), and the card says so in one clause.
- **Contributions.** From the interpretable model only. For a log-linear model, feature *j* contributes
  `β_j · (x_j − x̄_j)` in log price, shown in dollars as `benchmark · (exp(c_j) − 1)`. One-hot levels and the
  amenity families are grouped to one row each; the top 5 by absolute value are shown, the rest summed as
  "everything else".
- **Caveat panel** (draft wording): "Labels compare a listing's quoted price in the September 2026 Inside Airbnb
  snapshot with what similar listings in this city quoted at the same time. Each listing has one dated
  quote, not a rate card. The data record no bookings, so a label is relative market value, not a true
  price. Typical benchmark error in this city: ±$X per night."
- **Zoom.** Points at every zoom (WebGL handles 40k); the neighbourhood layer is a toggle, not an automatic
  low-zoom replacement, so the two views never silently swap.

## 5. Data contract: what modelling hands the map

The map reads one scored table per city and snapshot, produced by the modelling notebooks from
`strfair.prepare(city, snapshot)` and out-of-fold predictions (`docs/models.md` §3). Agreeing on this now
lets modelling (from Nov 1) and the map (from Nov 5) proceed in parallel.

| group | fields | from |
| ----- | ------ | ---- |
| identity | `id`, `name`, `listing_url`, `latitude`, `longitude`, `neighbourhood_cleansed` | `data.listings` |
| attributes | `room_type`, `accommodates`, `bedrooms`, `baths`, `review_scores_rating`, `number_of_reviews`, `superhost`, `km_to_centre` | `data.features` |
| quote context | `price`, `price_quote_checkin_date`, `quote_nights`, `lead_days`, `is_monthly_quote` | `data.features` |
| scores | `fair_interp`, `fair_ens` (dollars per night, out-of-fold), `ratio_interp`, `ratio_ens` | models |
| explanation | `contributions`: JSON string, a list of up to 5 `[name, usd]` plus `["Everything else", usd]`, summing to `fair_interp − base_price` | interpretable model |
| comparables | `comps`: JSON string, a list of up to 5 listing ids | post-processing |
| base | `base_price`: the typical listing the waterfall starts from (geometric mean price of the same stay type) | interpretable model |

The between-release fields are **not** part of the contract: `build_map_data.py` joins the previous release's
scored table on `id` itself (`ratio_interp_prev`, `ratio_ens_prev`, `price_prev`, `fair_interp_prev`), so a
modelling notebook scores one snapshot and knows nothing about the other. `property_group` and `n_amenities`
are optional extras the card uses when present.

One small side file per city: **metrics** (listings in sample, mean and median absolute error per model,
median absolute percent error, share per label at the default band, label-agreement share between models,
between-release label-kept share, the base prices). Neighbourhood aggregates are *not* precomputed: the
browser groups the listings currently shown, so the choropleth follows the filters and the band slider, and
the Inside Airbnb GeoJSON polygons are copied as they are.

Sizes, measured on Los Angeles (the largest city) with the fields above and 5 contributions per listing:
row-oriented JSON 30 MB raw / 3.2 MB gzipped; column-oriented JSON 15 MB / 2.1 MB gzipped. Column-oriented
it is, one file per city loaded on demand. As built, the files are 1.1 MB (Jersey City) to 19 MB (Los
Angeles) uncompressed: the readable contribution names cost more than the estimate, and GitHub Pages serves
them gzipped at roughly a fifth of that. If Los Angeles feels slow, shorten the names or drop `comps` to ids
only; the layout stays.

```
site/
├── index.html, styles.css
├── app/            # ES modules, no framework, no build step:
│                   # main (wiring), state, data, filters, mapview, card, compare, hoods, charts, labels, format
└── data/           # git-ignored, written by scripts/build_map_data.py
    ├── cities.json                        # list of cities, snapshots, bounds, file names
    ├── <city>_<snapshot>.json             # the scored table, column-oriented; ids as strings
    ├── <city>_<snapshot>.metrics.json
    ├── <city>.neighbourhoods.geojson      # copied from the snapshot folder
    └── attractions.json                   # optional, scripts/build_attractions.py
```

`scripts/build_map_data.py <city> <snapshot>` reads the scored table (parquet written by
`scripts/build_scored.py` under `data/scored/<city>_<snapshot>/`) and writes `site/data/`. That is the last stage of the
"one command from download to map" promise, and it is the only code that knows both the model output and
the map's file format. `scripts/stub_scores.py` writes a placeholder table in
the same format (ridge + a small random forest, out-of-fold); the map says so in its metrics strip and
caveat panel whenever it is showing stub scores.

## 6. Stack

| part | choice | why |
| ---- | ------ | --- |
| map | MapLibre GL JS with a GeoJSON source and a circle layer | WebGL draws 40k points without clustering; no API token; filters via `setFilter` without re-uploading data |
| basemap | OpenFreeMap or Carto light tiles | free, no key |
| charts on the card | D3 (waterfall, ratio histogram) | the course's tool; small |
| app | vanilla ES modules, one `index.html` | no build step, so a teammate who did not write it can still run it with `python -m http.server` |
| hosting | GitHub Pages from `site/` | free, static, matches the proposal's cost section |

## 7. Plan

| when | what | needs |
| ---- | ---- | ----- |
| done 2026-10-31 | the whole feature set of §3 over placeholder scores, all six cities, March 2026 joined for NYC / LA / Toronto | – |
| Nov 5–12 | swap in the real scored tables; review the card wording with the team; trim Los Angeles if slow | the modelling notebooks writing the §5 contract |
| progress report | the prototype deployed on GitHub Pages | – |
| Nov 12–19 | deploy to GitHub Pages (decide whether `site/data/` is committed or built in CI); accessibility pass; dark mode if wanted | – |
| Nov 19–26 | review-sentiment on the card if that pipeline lands; polish from the user test | Stella's per-listing sentiment |
| after | user test on the deployed map; fixes from it | – |

## 8. Open questions for the team

- Default band width: 0.20 from the pilot, or whatever the sensitivity analysis recommends.
- Prototype city: San Diego as suggested, or a stability-check city (Toronto) so the between-release view
  can be tried early.
- Thumbnails from `picture_url`: hot-linking Airbnb's CDN may stop working at any time; decide at the end.
- Review sentiment on the card once Stella's pipeline (notebook 03) produces a per-listing score: shown as
  context next to the rating, not as a model input, unless the modelling track includes it.
- Whether the compare basket should persist across city switches (probably not: nothing compares across
  cities).
