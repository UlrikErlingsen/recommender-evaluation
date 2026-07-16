"""Input contracts and temporal fold construction."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .errors import DataProblem


EVENT_REQUIRED = ("user_id", "item_id", "timestamp")
ITEM_REQUIRED = ("item_id", "item_name")


@dataclass(frozen=True)
class EvaluationConfig:
    """Predeclared choices for an offline temporal evaluation.

    Note: despite their names, ``min_train_events`` and ``cold_user_max_events``
    are thresholds on the number of UNIQUE pre-cutoff items a user interacted
    with, not on raw event counts. ``cold_item_max_events`` counts raw
    pre-cutoff training events for an item.
    """

    k: int = 10
    n_folds: int = 3
    initial_train_fraction: float = 0.60
    min_train_events: int = 3
    cold_user_max_events: int = 5
    cold_item_max_events: int = 3
    bootstrap_repetitions: int = 500
    hybrid_popularity_weight: float = 0.20
    hybrid_content_weight: float = 0.35
    hybrid_collaborative_weight: float = 0.45
    reference_policy: str = "Popularity"

    def __post_init__(self) -> None:
        if not 1 <= self.k <= 100:
            raise DataProblem("K must be between 1 and 100.")
        if not 1 <= self.n_folds <= 5:
            raise DataProblem("Use between 1 and 5 temporal folds.")
        if not 0.50 <= self.initial_train_fraction <= 0.90:
            raise DataProblem("The initial training fraction must be between 0.50 and 0.90.")
        if self.min_train_events < 1:
            raise DataProblem("Minimum training events must be positive.")
        if self.cold_user_max_events < self.min_train_events:
            raise DataProblem("The cold-user ceiling cannot be below the minimum training history.")
        if self.cold_item_max_events < 0:
            raise DataProblem("The cold-item ceiling cannot be negative.")
        if not 100 <= self.bootstrap_repetitions <= 5000:
            raise DataProblem("Bootstrap repetitions must be between 100 and 5,000.")
        weights = np.array(
            [
                self.hybrid_popularity_weight,
                self.hybrid_content_weight,
                self.hybrid_collaborative_weight,
            ],
            dtype=float,
        )
        if (weights < 0).any() or not np.isclose(weights.sum(), 1.0, atol=1e-6):
            raise DataProblem("Hybrid weights must be nonnegative and sum to 1.")
        if self.reference_policy not in {"Popularity", "Content-based", "Collaborative", "Hybrid"}:
            raise DataProblem("Choose one of the four declared policies as the reference.")


@dataclass(frozen=True)
class TemporalFold:
    fold: int
    train_end: pd.Timestamp
    test_end: pd.Timestamp


@dataclass
class ValidatedData:
    events: pd.DataFrame
    items: pd.DataFrame
    feature_columns: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class DataAudit:
    overview: pd.DataFrame
    subgroup_counts: pd.DataFrame
    item_availability: pd.DataFrame
    warnings: list[str]


def _missing_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> list[str]:
    return [column for column in required if column not in frame.columns]


def validate_inputs(events: pd.DataFrame, items: pd.DataFrame) -> ValidatedData:
    """Validate and standardize an implicit-feedback log and item catalog."""

    events = events.copy()
    items = items.copy()
    missing_events = _missing_columns(events, EVENT_REQUIRED)
    missing_items = _missing_columns(items, ITEM_REQUIRED)
    if missing_events:
        raise DataProblem(f"Interaction data are missing: {', '.join(missing_events)}.")
    if missing_items:
        raise DataProblem(f"Item data are missing: {', '.join(missing_items)}.")
    if events.empty or items.empty:
        raise DataProblem("Interaction data and the item catalog must both contain rows.")

    for column in ("user_id", "item_id"):
        if events[column].isna().any():
            raise DataProblem(f"{column} cannot contain missing values.")
        events[column] = events[column].astype(str).str.strip()
        if events[column].eq("").any():
            raise DataProblem(f"{column} cannot contain blank values.")
    for column in ("item_id", "item_name"):
        if items[column].isna().any():
            raise DataProblem(f"Item catalog column {column} cannot contain missing values.")
        items[column] = items[column].astype(str).str.strip()
        if items[column].eq("").any():
            raise DataProblem(f"Item catalog column {column} cannot contain blank values.")

    if items["item_id"].duplicated().any():
        duplicate = items.loc[items["item_id"].duplicated(), "item_id"].iloc[0]
        raise DataProblem(f"Item IDs must be unique; duplicate found: {duplicate}.")

    try:
        events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    except Exception as exc:
        raise DataProblem("Timestamps must be valid dates or datetimes.") from exc
    if events["timestamp"].nunique() < 8:
        raise DataProblem("At least eight distinct event timestamps are required for temporal holdouts.")
    exact_key = ["user_id", "item_id", "timestamp"]
    if events.duplicated(exact_key).any():
        raise DataProblem("Exact user-item-timestamp duplicates must be removed before evaluation.")

    if "event_weight" not in events:
        events["event_weight"] = 1.0
    events["event_weight"] = pd.to_numeric(events["event_weight"], errors="coerce")
    if events["event_weight"].isna().any() or (~np.isfinite(events["event_weight"])).any():
        raise DataProblem("Event weights must be finite numeric values.")
    if (events["event_weight"] <= 0).any():
        raise DataProblem("Event weights must be strictly positive.")

    warnings: list[str] = []
    if "subgroup" not in events:
        events["subgroup"] = "All users"
        warnings.append("No subgroup column was supplied; subgroup reporting uses one all-user group.")
    events["subgroup"] = events["subgroup"].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    subgroup_stability = events.groupby("user_id", observed=True)["subgroup"].nunique()
    if (subgroup_stability > 1).any():
        unstable = subgroup_stability[subgroup_stability > 1].index[0]
        raise DataProblem(f"Each user must have one stable subgroup label; {unstable} has several.")

    event_items = set(events["item_id"])
    catalog_items = set(items["item_id"])
    missing_catalog = sorted(event_items - catalog_items)
    if missing_catalog:
        preview = ", ".join(missing_catalog[:5])
        raise DataProblem(f"Every interacted item must be in the catalog. Missing: {preview}.")

    if "available_at" not in items:
        items["available_at"] = events["timestamp"].min() - pd.Timedelta(days=1)
        warnings.append(
            "No item availability timestamp was supplied; the app assumes the full catalog was available before the log began."
        )
    else:
        try:
            items["available_at"] = pd.to_datetime(items["available_at"], utc=True, errors="raise")
        except Exception as exc:
            raise DataProblem("Item available_at values must be valid dates or datetimes.") from exc

    availability = items.set_index("item_id")["available_at"]
    event_availability = events["item_id"].map(availability)
    if (events["timestamp"] < event_availability).any():
        bad_row = events.loc[events["timestamp"] < event_availability].iloc[0]
        raise DataProblem(f"Item {bad_row['item_id']} has an interaction before its declared availability.")

    feature_columns = sorted(column for column in items.columns if column.startswith("feature_"))
    if not feature_columns:
        raise DataProblem("The catalog needs at least one numeric feature_ column for the content-based policy.")
    for column in feature_columns:
        items[column] = pd.to_numeric(items[column], errors="coerce")
    matrix = items[feature_columns].to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise DataProblem("Content feature columns must contain finite numeric values without missing cells.")
    if np.allclose(matrix, 0):
        raise DataProblem("At least one content feature value must be nonzero.")
    if len(items) > 2500:
        raise DataProblem(
            "This transparent baseline workbench supports at most 2,500 catalog items; use a production-scale evaluator for larger catalogs."
        )

    if events["user_id"].nunique() < 5:
        raise DataProblem("At least five users are required for policy comparison.")
    if events["item_id"].nunique() < 5:
        raise DataProblem("At least five interacted items are required for policy comparison.")

    events = events.sort_values(["timestamp", "user_id", "item_id"], kind="mergesort").reset_index(drop=True)
    items = items.sort_values("item_id", kind="mergesort").reset_index(drop=True)
    warnings.extend(
        [
            "Implicit logs record observed behavior under earlier exposure policies; unobserved items are not proven dislikes.",
            "Item features must represent information that was genuinely available at each recommendation time.",
        ]
    )
    return ValidatedData(events=events, items=items, feature_columns=feature_columns, warnings=warnings)


def make_temporal_folds(events: pd.DataFrame, config: EvaluationConfig) -> list[TemporalFold]:
    """Create expanding-window global-timeline folds with nonoverlapping test windows."""

    timestamps = pd.Index(events["timestamp"].sort_values().unique())
    initial_index = int(np.floor(len(timestamps) * config.initial_train_fraction))
    initial_index = min(max(initial_index, 2), len(timestamps) - config.n_folds)
    if len(timestamps) - initial_index < config.n_folds:
        raise DataProblem("There are too few distinct timestamps for the requested temporal folds.")
    boundaries = np.linspace(initial_index, len(timestamps), config.n_folds + 1, dtype=int)
    if len(set(boundaries)) != len(boundaries):
        raise DataProblem("The requested temporal folds collapse onto the same timestamp.")

    folds: list[TemporalFold] = []
    for index in range(config.n_folds):
        train_end = pd.Timestamp(timestamps[boundaries[index]])
        if boundaries[index + 1] < len(timestamps):
            test_end = pd.Timestamp(timestamps[boundaries[index + 1]])
        else:
            test_end = pd.Timestamp(timestamps[-1]) + pd.to_timedelta(1, unit="ns")
        folds.append(TemporalFold(fold=index + 1, train_end=train_end, test_end=test_end))
    return folds


def audit_data(data: ValidatedData) -> DataAudit:
    events = data.events
    items = data.items
    users = events["user_id"].nunique()
    interacted_items = events["item_id"].nunique()
    unique_pairs = events[["user_id", "item_id"]].drop_duplicates().shape[0]
    density = unique_pairs / (users * len(items)) if users and len(items) else np.nan
    overview = pd.DataFrame(
        [
            {"measure": "Events", "value": len(events)},
            {"measure": "Users", "value": users},
            {"measure": "Catalog items", "value": len(items)},
            {"measure": "Interacted items", "value": interacted_items},
            {"measure": "Content features", "value": len(data.feature_columns)},
            {"measure": "User-item density", "value": density},
            {"measure": "First event", "value": events["timestamp"].min().isoformat()},
            {"measure": "Last event", "value": events["timestamp"].max().isoformat()},
        ]
    )
    subgroup_counts = (
        events[["user_id", "subgroup"]]
        .drop_duplicates()
        .groupby("subgroup", observed=True)
        .size()
        .rename("users")
        .reset_index()
        .sort_values("users", ascending=False)
    )
    item_availability = (
        items.assign(available_month=items["available_at"].dt.strftime("%Y-%m"))
        .groupby("available_month", observed=True)
        .size()
        .rename("items_becoming_available")
        .reset_index()
    )
    return DataAudit(
        overview=overview,
        subgroup_counts=subgroup_counts,
        item_availability=item_availability,
        warnings=list(data.warnings),
    )
