"""Fit the project RF per pinned city + one pooled model; write importance tables.

Mirrors notebooks/05_random_forest.ipynb feature rules (drop LEAKY / DEMAND_RESPONSE / ids).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strfair  # noqa: E402

OUT = ROOT / "docs" / "eda"
OUT.mkdir(parents=True, exist_ok=True)

DROP_EXTRA = ["neighbourhood_raw"]
RF_KW = dict(
    n_estimators=300,
    max_depth=20,
    min_samples_leaf=5,
    max_features="sqrt",
    n_jobs=-1,
    random_state=42,
)


def feature_matrix(F: pd.DataFrame, *, keep_city: bool = False) -> tuple[pd.DataFrame, list[str], list[str]]:
    drop = set(strfair.LEAKY) | set(strfair.DEMAND_RESPONSE) | set(strfair.ID_COLUMNS) | set(DROP_EXTRA)
    if keep_city:
        drop.discard("city")
    X_cols = [c for c in F.columns if c not in drop]
    cat = list(F[X_cols].select_dtypes(exclude="number").columns)
    num = [c for c in X_cols if c not in cat]
    return F[X_cols], num, cat


def make_model(num: list[str], cat: list[str]) -> any:
    pre = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False), cat),
        ]
    )
    return make_pipeline(pre, RandomForestRegressor(**RF_KW))


def importances_series(model, num: list[str], cat: list[str]) -> pd.Series:
    ohe = model.named_steps["columntransformer"].named_transformers_["cat"]
    names = list(num) + list(ohe.get_feature_names_out(cat))
    return pd.Series(
        model.named_steps["randomforestregressor"].feature_importances_,
        index=names,
        name="importance",
    ).sort_values(ascending=False)


def collapse_onehots(imp: pd.Series, num: list[str], cat: list[str]) -> pd.Series:
    """Sum one-hot pieces back to the parent categorical name; keep numerics as-is.

    Match longest categorical prefix first so ``room_type_*`` is not eaten by ``room_``.
    """
    out: dict[str, float] = {c: float(imp.get(c, 0.0)) for c in num}
    for c in cat:
        out[c] = 0.0
    cats_by_len = sorted(cat, key=len, reverse=True)
    for name, val in imp.items():
        if name in out and name not in cat:
            continue
        matched = None
        for c in cats_by_len:
            if name == c or name.startswith(f"{c}_"):
                matched = c
                break
        if matched is not None:
            out[matched] = out.get(matched, 0.0) + float(val)
        elif name in num:
            out[name] = float(val)
    return pd.Series(out, name="importance").sort_values(ascending=False)


def eval_holdout(model, X: pd.DataFrame, y: pd.Series, price: pd.Series) -> dict:
    """One 80/20 holdout (faster than 5-fold); importances still fit on full sample later."""
    X_tr, X_te, y_tr, y_te, p_tr, p_te = train_test_split(
        X, y, price, test_size=0.2, random_state=42
    )
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    return {
        "rmse_log": float(mean_squared_error(y_te, pred) ** 0.5),
        "mae_log": float(mean_absolute_error(y_te, pred)),
        "mae_usd": float(mean_absolute_error(p_te, np.exp(pred))),
        "n": int(len(y)),
    }


def run_one(city: str, snapshot: str) -> tuple[dict, pd.Series, pd.Series, pd.DataFrame]:
    data = strfair.prepare(city, snapshot, verbose=True)
    F = data.features.copy()
    X, num, cat = feature_matrix(F)
    y = F["log_price"]
    model = make_model(num, cat)
    metrics = eval_holdout(model, X, y, F["price"])
    metrics.update(city=city, snapshot=snapshot, n_features=len(num) + len(cat))
    model.fit(X, y)  # full-sample fit for importances
    raw = importances_series(model, num, cat)
    collapsed = collapse_onehots(raw, num, cat)
    return metrics, raw, collapsed, F.assign(_city=city)


def main() -> None:
    metrics_rows = []
    top_raw_rows = []
    collapsed_by_city: dict[str, pd.Series] = {}
    frames = []

    for city, snapshot in strfair.PINNED_SNAPSHOTS.items():
        print(f"\n=== {city} @ {snapshot} ===")
        metrics, raw, collapsed, F = run_one(city, snapshot)
        metrics_rows.append(metrics)
        collapsed_by_city[city] = collapsed
        frames.append(F)
        for rank, (feat, val) in enumerate(raw.head(20).items(), 1):
            top_raw_rows.append(
                {"city": city, "snapshot": snapshot, "rank": rank, "feature": feat, "importance": val}
            )
        print(
            f"OOF RMSE(log)={metrics['rmse_log']:.3f}  MAE(log)={metrics['mae_log']:.3f}  "
            f"MAE($)=${metrics['mae_usd']:,.0f}  n={metrics['n']:,}"
        )
        print("top 10 collapsed:", ", ".join(f"{k}={v:.3f}" for k, v in collapsed.head(10).items()))

    metrics_df = pd.DataFrame(metrics_rows)
    top_raw_df = pd.DataFrame(top_raw_rows)

    # Consensus: mean collapsed importance across cities (0 if missing in a city)
    all_feats = sorted({f for s in collapsed_by_city.values() for f in s.index})
    cons = pd.DataFrame({c: s.reindex(all_feats).fillna(0.0) for c, s in collapsed_by_city.items()})
    cons["mean_importance"] = cons.mean(axis=1)
    cons["n_cities_nonzero"] = (cons.drop(columns="mean_importance") > 0).sum(axis=1)
    cons = cons.sort_values("mean_importance", ascending=False)

    # Pooled RF (all cities), keep city as a feature
    print("\n=== pooled (all 6 cities) ===")
    pooled = pd.concat(frames, ignore_index=True)
    # ensure city column present for keep_city
    if "city" not in pooled.columns:
        pooled["city"] = pooled["_city"]
    X, num, cat = feature_matrix(pooled, keep_city=True)
    y = pooled["log_price"]
    model = make_model(num, cat)
    pooled_metrics = eval_holdout(model, X, y, pooled["price"])
    pooled_metrics.update(city="POOL", snapshot="pinned", n_features=len(num) + len(cat))
    metrics_df = pd.concat([metrics_df, pd.DataFrame([pooled_metrics])], ignore_index=True)
    model.fit(X, y)
    pooled_raw = importances_series(model, num, cat)
    pooled_collapsed = collapse_onehots(pooled_raw, num, cat)

    metrics_df.to_csv(OUT / "rf_metrics_by_city.csv", index=False)
    top_raw_df.to_csv(OUT / "rf_top20_importances_by_city.csv", index=False)
    cons.to_csv(OUT / "rf_collapsed_importance_consensus.csv")
    pooled_raw.head(30).to_csv(OUT / "rf_pooled_top_importances_raw.csv", header=True)
    pooled_collapsed.head(30).to_csv(OUT / "rf_pooled_top_importances_collapsed.csv", header=True)

    print(
        f"POOL OOF RMSE(log)={pooled_metrics['rmse_log']:.3f}  "
        f"MAE(log)={pooled_metrics['mae_log']:.3f}  MAE($)=${pooled_metrics['mae_usd']:,.0f}  "
        f"n={pooled_metrics['n']:,}"
    )
    print("\nConsensus top 15 (mean collapsed importance across cities):")
    print(cons["mean_importance"].head(15).to_string())
    print("\nPooled top 15 (collapsed):")
    print(pooled_collapsed.head(15).to_string())
    print(f"\nWrote tables under {OUT}")


if __name__ == "__main__":
    main()
