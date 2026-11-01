
"""Reusable Airbnb review sentiment features (VADER baseline)."""

import html
import re

import numpy as np
import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DetectorFactory.seed = 42

def _clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def clean_reviews(reviews: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    """Filter reviews to usable English text available by the snapshot date.

    Excludes reviews with five or fewer words.
    """
    required = {"listing_id", "date", "comments"}
    missing = required.difference(reviews.columns)
    if missing:
        raise ValueError(f"Missing review columns: {sorted(missing)}")

    cutoff = pd.Timestamp(snapshot_date)
    if cutoff.tzinfo is not None:
        raise ValueError("snapshot_date must be a timezone-naive date")

    df = reviews.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].dt.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)

    # Only reviews available by the snapshot date
    df = df[df["date"].notna() & df["date"].le(cutoff)].copy()

    # Remove missing listing IDs and comments
    df = df.dropna(subset=["listing_id", "comments"]).copy()

    # Clean HTML and whitespace
    df["clean_text"] = df["comments"].astype(str).map(_clean_text)

    # Exclude reviews with five or fewer words
    df = df[df["clean_text"].str.split().str.len().gt(5)].copy()

    # Keep English reviews only
    df["language"] = df["clean_text"].map(_detect_language)
    return df[df["language"].eq("en")].copy()


def score_reviews(cleaned_reviews: pd.DataFrame) -> pd.DataFrame:
    """Assign VADER scores and sentiment labels."""
    if "clean_text" not in cleaned_reviews:
        raise ValueError("cleaned_reviews must contain clean_text")

    df = cleaned_reviews.copy()
    analyzer = SentimentIntensityAnalyzer()

    df["sentiment_score"] = df["clean_text"].map(
        lambda text: analyzer.polarity_scores(text)["compound"]
    )

    df["sentiment_label"] = np.select(
        [df["sentiment_score"].ge(0.05),
         df["sentiment_score"].le(-0.05)],
        ["Positive", "Negative"],
        default="Neutral",
    )

    return df


def aggregate_sentiment(
    scored_reviews: pd.DataFrame,
    snapshot_date: str,
    half_life_days: int = 730
) -> pd.DataFrame:
    """Aggregate scored reviews into one feature row per listing."""

    required = {"listing_id", "date", "sentiment_score"}
    missing = required.difference(scored_reviews.columns)

    if missing:
        raise ValueError(
            f"Missing scored-review columns: {sorted(missing)}"
        )

    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")

    df = scored_reviews.copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    cutoff = pd.Timestamp(snapshot_date)

    if df["date"].isna().any() or (df["date"] > cutoff).any():
        raise ValueError(
            "Review dates must be present and on/before snapshot"
        )

    if df["sentiment_score"].isna().any():
        raise ValueError("Sentiment scores cannot be missing")

    # Calculate recency weights
    df["review_age_days"] = (cutoff - df["date"]).dt.days

    df["recency_weight"] = (
        0.5 ** (df["review_age_days"] / half_life_days)
    )

    df["weighted_score"] = (
        df["sentiment_score"] * df["recency_weight"]
    )

    df["is_negative"] = (
        df["sentiment_score"].le(-0.05).astype(int)
    )

    # Aggregate to listing level
    features = df.groupby("listing_id").agg(
        sentiment_review_count=("sentiment_score", "size"),
        avg_sentiment=("sentiment_score", "mean"),
        sentiment_std=("sentiment_score", "std"),
        negative_review_pct=("is_negative", "mean"),
        weighted_score_sum=("weighted_score", "sum"),
        weight_sum=("recency_weight", "sum"),
    ).reset_index()

    features["weighted_sentiment"] = (
        features["weighted_score_sum"] / features["weight_sum"]
    )

    features["negative_review_pct"] *= 100

    # Keep only listings with at least 3 eligible reviews (for calculating std. deviation)
    MIN_REVIEWS = 3

    features = features[
        features["sentiment_review_count"] >= MIN_REVIEWS
    ].copy()

    return features.drop(
        columns=["weighted_score_sum", "weight_sum"]
    )


def build_sentiment_features(
    reviews: pd.DataFrame,
    snapshot_date: str,
    half_life_days: int = 730
) -> pd.DataFrame:
    """Full cleaning, VADER scoring, and aggregation pipeline."""

    cleaned = clean_reviews(reviews, snapshot_date)
    scored = score_reviews(cleaned)

    return aggregate_sentiment(
        scored,
        snapshot_date,
        half_life_days
    )
