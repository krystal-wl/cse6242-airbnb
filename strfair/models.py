"""
Feature lists and model builders for the two fair-price tracks.
Feature lists load from docs/eda/feature_lists/decisions.csv 
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DECISIONS_CSV = _REPO_ROOT / "docs" / "eda" / "feature_lists" / "decisions.csv"


def _load_feature_lists(path: Path = _DECISIONS_CSV) -> tuple[list[str], list[str], list[str]]:
    """Read CANDIDATES / ENET_FEATURES / RF_FEATURES from 05's decisions.csv."""
    df = pd.read_csv(path)
    for col in ("candidate", "elastic_net", "random_forest"):
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().str.lower().eq("true")
    candidates = df.loc[df["candidate"], "column"].tolist()
    enet = df.loc[df["elastic_net"], "column"].tolist()
    rf = df.loc[df["random_forest"], "column"].tolist()
    return candidates, enet, rf


CANDIDATES, ENET_FEATURES, RF_FEATURES = _load_feature_lists()

# EN / RF: June PINNED_SNAPSHOTS, all 6 cities (GroupKFold by host).
# EN best: alpha=0.0001, l1_ratio=1.0 (mean MAE 0.2940).
# RF best: n_estimators=500, min_samples_leaf=2, max_features=None (mean MAE 0.2783).
ENET_PARAMS: dict = {"alpha": 0.0001, "l1_ratio": 1.0, "max_iter": 5000}
RF_PARAMS: dict = {
    "n_estimators": 500,
    "min_samples_leaf": 2,
    "max_features": None,
    "n_jobs": -1,
    "random_state": 42,
}
ENET_TUNED: bool = True
RF_TUNED: bool = True
TUNED: bool = True



# Matrix helpers
def _ensure_no_sentiment(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    if "no_sentiment" not in out.columns and "avg_sentiment" in out.columns:
        out["no_sentiment"] = out["avg_sentiment"].isna().astype(int)
    for col in ("checkin_dow", "checkin_month"):
        if col in out.columns:
            out[col] = out[col].astype("object")
    return out


def feature_matrix(features: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Select model columns present in ``features``."""
    F = _ensure_no_sentiment(features)
    cols = [c for c in columns if c in F.columns]
    return F[cols].copy()


def _split_num_cat(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    cat = list(X.select_dtypes(exclude="number").columns)
    num = [c for c in X.columns if c not in cat]
    return num, cat



# Model builders (sklearn pipelines)
def make_elastic_net(X: pd.DataFrame, **overrides):
    """Elastic net on ``ENET_FEATURES``"""
    params = {**ENET_PARAMS, **overrides}
    num, cat = _split_num_cat(X)
    pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), cat),
    ])
    return make_pipeline(pre, ElasticNet(**params))


def make_random_forest(X: pd.DataFrame, **overrides):
    """Random forest on ``RF_FEATURES``"""
    params = {**RF_PARAMS, **overrides}
    num, cat = _split_num_cat(X)
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), num),
        ("cat", make_pipeline(
            SimpleImputer(strategy="most_frequent"),
            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
        ), cat),
    ])
    return make_pipeline(pre, RandomForestRegressor(**params))
