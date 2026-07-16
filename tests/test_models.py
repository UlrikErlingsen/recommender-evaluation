from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from recommendsignal.design import EvaluationConfig, TemporalFold, validate_inputs
from recommendsignal.models import POLICIES, _ndcg, evaluate_fold


def test_binary_ndcg_matches_hand_calculation() -> None:
    recommended = ["A", "B", "C"]
    relevant = {"B", "C"}
    observed = _ndcg(recommended, relevant, 3)
    expected = ((1 / np.log2(3)) + (1 / np.log2(4))) / ((1 / np.log2(2)) + (1 / np.log2(3)))
    assert observed == pytest.approx(expected)


def test_every_policy_produces_user_metrics(result) -> None:
    assert set(result.user_metrics["policy"]) == set(POLICIES)
    counts = result.user_metrics.groupby(["fold", "policy"]).size().unstack()
    assert counts.notna().all().all()


def test_slates_do_not_exceed_k(result) -> None:
    sizes = result.recommendations.groupby(["fold", "policy", "user_id"]).size()
    assert (sizes <= result.config.k).all()
    assert (sizes > 0).all()


def test_slates_exclude_pre_cutoff_history(result, validated) -> None:
    folds = result.folds.set_index("fold")
    sample = result.recommendations.iloc[:: max(len(result.recommendations) // 500, 1)]
    for row in sample.itertuples(index=False):
        cutoff = pd.Timestamp(folds.loc[row.fold, "train_before"])
        prior = validated.events.loc[
            (validated.events["user_id"] == row.user_id) & (validated.events["timestamp"] < cutoff), "item_id"
        ]
        assert row.item_id not in set(prior)


def test_slates_respect_item_availability(result, validated) -> None:
    availability = validated.items.set_index("item_id")["available_at"]
    folds = result.folds.set_index("fold")
    for row in result.recommendations.drop_duplicates(["fold", "item_id"]).itertuples(index=False):
        assert availability[row.item_id] <= pd.Timestamp(folds.loc[row.fold, "train_before"])


def test_user_ranking_metrics_are_bounded(result) -> None:
    for column in ("recall_at_k", "ndcg_at_k"):
        assert result.user_metrics[column].between(0, 1).all()


def test_cold_start_fields_are_explicit(result) -> None:
    assert result.user_metrics["cold_user"].dtype == bool
    assert result.user_metrics["n_cold_relevant_items"].ge(0).all()
    assert result.user_metrics["cold_item_recall_at_k"].notna().any()


def _canary_frames(include_burst: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixed-cutoff data where item ZHOT becomes massively popular only after the cutoff."""

    train_baskets = {
        "u1": ["I01", "I02", "I03"],
        "u2": ["I02", "I03", "I04"],
        "u3": ["I01", "I03", "I05"],
        "u4": ["I02", "I04", "I05"],
        "u5": ["I01", "I04", "I05"],
    }
    test_items = {"u1": "I05", "u2": "I01", "u3": "I04", "u4": "I03", "u5": "I02"}
    rows: list[dict[str, object]] = []
    tick = 0
    for user, basket in train_baskets.items():
        for item in basket:
            rows.append(
                {
                    "user_id": user,
                    "item_id": item,
                    "timestamp": pd.Timestamp("2026-05-01") + pd.Timedelta(int(tick), unit="h"),
                }
            )
            tick += 1
    for user, item in test_items.items():
        rows.append(
            {
                "user_id": user,
                "item_id": item,
                "timestamp": pd.Timestamp("2026-06-10") + pd.Timedelta(int(tick), unit="h"),
            }
        )
        tick += 1
    if include_burst:
        for burst in range(30):
            rows.append(
                {
                    "user_id": f"b{burst:02d}",
                    "item_id": "ZHOT",
                    "timestamp": pd.Timestamp("2026-07-01") + pd.Timedelta(int(burst), unit="h"),
                }
            )
    events = pd.DataFrame(rows)
    item_ids = [f"I{index:02d}" for index in range(1, 12)] + ["ZHOT"]
    items = pd.DataFrame(
        {
            "item_id": item_ids,
            "item_name": [f"Item {item_id}" for item_id in item_ids],
            "feature_1": np.arange(1.0, len(item_ids) + 1.0),
            "feature_2": 1.0,
            "available_at": pd.Timestamp("2026-01-01"),
        }
    )
    return events, items


def test_post_cutoff_popularity_burst_never_leaks_into_training() -> None:
    fold = TemporalFold(
        fold=1,
        train_end=pd.Timestamp("2026-06-01", tz="UTC"),
        test_end=pd.Timestamp("2026-08-01", tz="UTC"),
    )
    config = EvaluationConfig(k=2, n_folds=1, min_train_events=3, bootstrap_repetitions=100)
    with_burst = evaluate_fold(validate_inputs(*_canary_frames(True)), fold, config)
    without_burst = evaluate_fold(validate_inputs(*_canary_frames(False)), fold, config)

    # ZHOT is available before the cutoff but interacted with only afterwards:
    # a leaky popularity fit would place it at the top of every slate.
    popularity_slates = with_burst.recommendations.loc[
        with_burst.recommendations["policy"] == "Popularity", "item_id"
    ]
    assert "ZHOT" not in set(popularity_slates)

    # Training-side artifacts (popularity counts, the item-item similarity
    # matrix, content profiles, and novelty) must ignore test-window events,
    # so every slate and score is identical with or without the burst.
    pd.testing.assert_frame_equal(
        with_burst.recommendations.reset_index(drop=True),
        without_burst.recommendations.reset_index(drop=True),
    )
    assert with_burst.diagnostics["training_events"] == without_burst.diagnostics["training_events"]
