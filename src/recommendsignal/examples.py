"""Deterministic, wholly fictional RecommendSignal example data."""

from __future__ import annotations

import numpy as np
import pandas as pd


FEATURES = (
    "feature_practical",
    "feature_creative",
    "feature_premium",
    "feature_social",
    "feature_learning",
    "feature_wellbeing",
    "feature_adventure",
    "feature_calm",
)


def make_demo_catalog(seed: int = 6437) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01", tz="UTC")
    rows: list[dict[str, object]] = []
    for index in range(96):
        primary = index % len(FEATURES)
        secondary = int(rng.choice([candidate for candidate in range(len(FEATURES)) if candidate != primary]))
        availability_day = 0 if index < 58 else int(rng.integers(10, 225))
        row: dict[str, object] = {
            "item_id": f"ITEM-{index + 1:03d}",
            "item_name": f"Fictional selection {index + 1:03d}",
            "available_at": (start + pd.to_timedelta(availability_day, unit="D")).isoformat(),
        }
        for feature_index, feature in enumerate(FEATURES):
            row[feature] = 1.0 if feature_index == primary else 0.45 if feature_index == secondary else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def make_demo_events(seed: int = 6437) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    catalog = make_demo_catalog(seed)
    feature_matrix = catalog[list(FEATURES)].to_numpy(dtype=float)
    available_days = (
        pd.to_datetime(catalog["available_at"], utc=True) - pd.Timestamp("2025-01-01", tz="UTC")
    ).dt.days.to_numpy()
    base_popularity = np.exp(-np.arange(len(catalog)) / 24.0)
    rng.shuffle(base_popularity)
    item_ids = catalog["item_id"].to_numpy(dtype=str)
    start = pd.Timestamp("2025-01-01", tz="UTC")
    subgroup_specs = (
        ("New explorers", 16, 0.55),
        ("Focused regulars", 23, 0.30),
        ("Broad enthusiasts", 31, 0.18),
    )
    rows: list[dict[str, object]] = []

    for user_index in range(320):
        subgroup, average_events, taste_alpha = subgroup_specs[user_index % len(subgroup_specs)]
        event_count = int(np.clip(rng.poisson(average_events), 12, 38))
        first_day = int(rng.integers(0, 80 if subgroup != "New explorers" else 145))
        possible_days = np.arange(first_day, 365)
        event_count = min(event_count, len(possible_days))
        event_days = np.sort(rng.choice(possible_days, size=event_count, replace=False))
        taste = rng.dirichlet(np.full(len(FEATURES), taste_alpha))
        chosen: set[int] = set()

        for event_number, day in enumerate(event_days):
            candidates = np.array(
                [index for index in range(len(catalog)) if available_days[index] <= day and index not in chosen], dtype=int
            )
            if not len(candidates):
                break
            affinity = feature_matrix[candidates] @ taste
            log_popularity = np.log(base_popularity[candidates] + 1e-9)
            utility = 3.2 * affinity + 0.55 * log_popularity + rng.normal(0, 0.22, len(candidates))
            probabilities = np.exp(utility - utility.max())
            probabilities /= probabilities.sum()
            selected = int(rng.choice(candidates, p=probabilities))
            chosen.add(selected)

            strength = float(feature_matrix[selected] @ taste)
            interaction_probability = min(max(0.20 + 1.8 * strength, 0.0), 1.0)
            interaction_type = rng.choice(
                ["open", "save", "complete"],
                p=[1 - 0.55 * interaction_probability, 0.35 * interaction_probability, 0.20 * interaction_probability],
            )
            event_weight = {"open": 1.0, "save": 2.0, "complete": 3.0}[str(interaction_type)]
            minute_offset = int(day) * 24 * 60 + int(rng.integers(7, 23)) * 60 + event_number
            timestamp = start + pd.to_timedelta(minute_offset, unit="m")
            rows.append(
                {
                    "user_id": f"USER-{user_index + 1:04d}",
                    "item_id": item_ids[selected],
                    "timestamp": timestamp.isoformat(),
                    "event_weight": event_weight,
                    "event_type": str(interaction_type),
                    "subgroup": subgroup,
                }
            )
    return pd.DataFrame(rows).sort_values(["timestamp", "user_id"], kind="mergesort").reset_index(drop=True)


def make_event_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "user_id": "USER-001",
                "item_id": "ITEM-001",
                "timestamp": "2026-01-05T09:00:00Z",
                "event_weight": 1.0,
                "event_type": "open",
                "subgroup": "Declared cohort A",
            },
            {
                "user_id": "USER-001",
                "item_id": "ITEM-002",
                "timestamp": "2026-01-12T09:00:00Z",
                "event_weight": 2.0,
                "event_type": "save",
                "subgroup": "Declared cohort A",
            },
        ]
    )


def make_catalog_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "item_id": "ITEM-001",
                "item_name": "Example item one",
                "available_at": "2025-12-01T00:00:00Z",
                "feature_topic_a": 1.0,
                "feature_topic_b": 0.0,
            },
            {
                "item_id": "ITEM-002",
                "item_name": "Example item two",
                "available_at": "2025-12-01T00:00:00Z",
                "feature_topic_a": 0.0,
                "feature_topic_b": 1.0,
            },
        ]
    )
