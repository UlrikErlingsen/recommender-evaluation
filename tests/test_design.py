from __future__ import annotations

import pandas as pd
import pytest

from recommendsignal.design import EvaluationConfig, audit_data, make_temporal_folds, validate_inputs
from recommendsignal.errors import DataProblem


def test_valid_demo_contract(validated) -> None:
    assert len(validated.feature_columns) == 8
    assert str(validated.events["timestamp"].dtype).startswith("datetime64[ns, UTC]")
    assert validated.items["item_id"].is_unique


def test_audit_reports_core_dimensions(validated) -> None:
    audit = audit_data(validated)
    measures = set(audit.overview["measure"])
    assert {"Events", "Users", "Catalog items", "Content features"}.issubset(measures)
    assert audit.subgroup_counts["users"].sum() == validated.events["user_id"].nunique()


def test_temporal_folds_are_ordered_and_nonoverlapping(validated, config) -> None:
    folds = make_temporal_folds(validated.events, config)
    assert len(folds) == 3
    for fold in folds:
        assert fold.train_end < fold.test_end
    assert folds[0].test_end == folds[1].train_end
    assert folds[1].test_end == folds[2].train_end


def test_duplicate_event_is_rejected(demo_events, demo_catalog) -> None:
    duplicate = pd.concat([demo_events, demo_events.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataProblem, match="duplicates"):
        validate_inputs(duplicate, demo_catalog)


def test_missing_content_features_are_rejected(demo_events, demo_catalog) -> None:
    catalog = demo_catalog[["item_id", "item_name", "available_at"]]
    with pytest.raises(DataProblem, match="feature_"):
        validate_inputs(demo_events, catalog)


def test_nonpositive_event_weight_is_rejected(demo_events, demo_catalog) -> None:
    events = demo_events.copy()
    events.loc[0, "event_weight"] = 0
    with pytest.raises(DataProblem, match="strictly positive"):
        validate_inputs(events, demo_catalog)


def test_unstable_user_subgroup_is_rejected(demo_events, demo_catalog) -> None:
    events = demo_events.copy()
    user = events.loc[0, "user_id"]
    indices = events.index[events["user_id"] == user]
    events.loc[indices[-1], "subgroup"] = "Different group"
    with pytest.raises(DataProblem, match="stable subgroup"):
        validate_inputs(events, demo_catalog)


def test_interaction_before_item_availability_is_rejected(demo_events, demo_catalog) -> None:
    catalog = demo_catalog.copy()
    item_id = demo_events.loc[0, "item_id"]
    catalog.loc[catalog["item_id"] == item_id, "available_at"] = "2026-01-01T00:00:00Z"
    with pytest.raises(DataProblem, match="before its declared availability"):
        validate_inputs(demo_events, catalog)


def test_hybrid_weights_must_sum_to_one() -> None:
    with pytest.raises(DataProblem, match="sum to 1"):
        EvaluationConfig(
            hybrid_popularity_weight=0.4,
            hybrid_content_weight=0.4,
            hybrid_collaborative_weight=0.4,
        )
