# Candidate models (interpretable vs ensemble)

*Companion to* `[docs/features.md](features.md)`*.* 

**Target:** `log(price)` on priced snapshots only, with price clipped to about $10–$10,000. Quote-timing controls (`lead_days`, `quote_nights` / stay length, `minimum_nights`) stay in so monthly discounts are not mistaken for “cheap listings.” Demand columns (availability, recent review velocity) are for **validation**, not inputs.

We keep two tracks: an **interpretable** model (readable effects) and an **ensemble** model (accuracy). Same allowed feature set from `features.md` for both.

---

## 1. Interpretable candidates


| Model                     | Package                    | What you get                                                  | Notes for this project                                                       |
| ------------------------- | -------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **OLS / log-linear**      | `statsmodels`              | Coefs ≈ % change in price per feature                         | Clearest story; watch multicollinearity and overfit on small cities          |
| **Ridge / Elastic net**   | `sklearn`                  | Same linear story; shrinkage; elastic net can zero weak coefs | Prefer over plain OLS once the feature count grows (one-hots, caveats)       |
| **GAM / EBM**             | `interpret` (optional dep) | Smooth shape per feature, still plotable                      | Good middle ground if linear fits miss curves (e.g. distance, size)          |
| **Shallow decision tree** | `sklearn`                  | Short if/else rules                                           | Cap depth (e.g. ≤ 4); use for intuition, not as the only interpretable model |


**Interpretable defaults to try first:** log-linear OLS (baseline story) → elastic net (main interpretable horse). EBM and shallow tree are optional extras.

---

## 2. Ensemble candidates


| Model             | Package   | What you get                                    | Notes for this project                                                           |
| ----------------- | --------- | ----------------------------------------------- | -------------------------------------------------------------------------------- |
| **Random forest** | `sklearn` | Nonlinear interactions, strong tabular baseline | Only ensemble in scope for now; modest depth / enough trees; no scaling required |


Raw lat/lon (and richer location encodings) are fine as RF inputs even when the interpretable model uses distance-to-centre instead.

---

## 3. Evaluation protocol

- **Split:** hold out a fraction of listings (e.g. 20–25%), stratified by city when training pooled; also report **per-city** error so Jersey City / Vegas are not hidden by NYC/LA.
- **Metrics:** RMSE and MAE on `log_price`; also MAE on dollars (`exp` of predictions) for a host-facing number.
- **Slices worth reporting:** monthly vs nightly quotes; city; maybe room type. Matches open questions in `features.md`.
- **Stability:** if multiple priced snapshots exist, check that rankings of errors do not flip wildly Mar vs Jun 2026 (Sep 2025 treated separately if used).
- **Validation-only check (not training inputs):** under-priced listings (vs model) should tend to show stronger demand proxies (availability / recent reviews), as in the proposal framing in `features.md`.

---

## 4. Recommendation


| Track         | Primary pick                 | Backup                           |
| ------------- | ---------------------------- | -------------------------------- |
| Interpretable | **Elastic net** on log price | OLS for the simplest coef table; |
| Ensemble      | **Random forest**            | only candidate for now           |


Elastic net explains a fair price; random forest checks how much accuracy we leave on the table with the same honest features.

---

## 5. Later

- Amenities flags and review-text sentiment as model inputs until those pipelines exist
- Using availability or `estimated_revenue_*` as predictors

