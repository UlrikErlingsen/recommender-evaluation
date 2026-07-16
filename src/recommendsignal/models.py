"""Transparent baseline recommendation policies."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse

from .design import EvaluationConfig, TemporalFold, ValidatedData


POLICIES = ("Popularity", "Content-based", "Collaborative", "Hybrid")


@dataclass
class FoldOutput:
    recommendations: pd.DataFrame
    user_metrics: pd.DataFrame
    diagnostics: dict[str, object]


def _unit_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return np.divide(values, norms, out=np.zeros_like(values, dtype=float), where=norms > 0)


def _relative_rank(scores: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Map candidate scores to [0, 1] ranks without using test outcomes."""

    result = np.zeros_like(scores, dtype=float)
    values = scores[candidates]
    if len(values) <= 1:
        result[candidates] = 1.0
        return result
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.linspace(0.0, 1.0, len(values))
    result[candidates] = ranks
    return result


def _ndcg(recommended: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return np.nan
    dcg = sum(1.0 / np.log2(rank + 2.0) for rank, item in enumerate(recommended[:k]) if item in relevant)
    ideal_length = min(len(relevant), k)
    ideal = sum(1.0 / np.log2(rank + 2.0) for rank in range(ideal_length))
    return float(dcg / ideal) if ideal else np.nan


def _score_catalog(
    history_indices: np.ndarray,
    history_weights: np.ndarray,
    popularity: np.ndarray,
    features: np.ndarray,
    item_similarity: np.ndarray,
    candidates: np.ndarray,
    config: EvaluationConfig,
) -> tuple[dict[str, np.ndarray], dict[str, bool]]:
    pop_scores = np.log1p(popularity)

    profile = (features[history_indices] * history_weights[:, None]).sum(axis=0)
    profile_norm = np.linalg.norm(profile)
    content_scores = features @ (profile / profile_norm) if profile_norm > 0 else np.zeros(len(features))

    collaborative_scores = item_similarity[:, history_indices] @ history_weights
    fallbacks = {
        "Popularity": False,
        "Content-based": bool(np.ptp(content_scores[candidates]) <= 1e-12),
        "Collaborative": bool(np.ptp(collaborative_scores[candidates]) <= 1e-12),
    }
    fallbacks["Hybrid"] = fallbacks["Content-based"] or fallbacks["Collaborative"]
    if fallbacks["Content-based"]:
        content_scores = pop_scores.copy()
    if fallbacks["Collaborative"]:
        collaborative_scores = pop_scores.copy()

    ranked_pop = _relative_rank(pop_scores, candidates)
    ranked_content = _relative_rank(content_scores, candidates)
    ranked_collaborative = _relative_rank(collaborative_scores, candidates)
    hybrid_scores = (
        config.hybrid_popularity_weight * ranked_pop
        + config.hybrid_content_weight * ranked_content
        + config.hybrid_collaborative_weight * ranked_collaborative
    )
    return (
        {
            "Popularity": pop_scores,
            "Content-based": content_scores,
            "Collaborative": collaborative_scores,
            "Hybrid": hybrid_scores,
        },
        fallbacks,
    )


def evaluate_fold(data: ValidatedData, fold: TemporalFold, config: EvaluationConfig) -> FoldOutput:
    """Fit four baselines before a cutoff and replay the following window."""

    events = data.events
    train = events.loc[events["timestamp"] < fold.train_end].copy()
    raw_test = events.loc[(events["timestamp"] >= fold.train_end) & (events["timestamp"] < fold.test_end)].copy()
    catalog = data.items.loc[data.items["available_at"] <= fold.train_end].copy()
    eligible_item_ids = sorted(catalog["item_id"].astype(str))
    eligible_set = set(eligible_item_ids)
    train = train.loc[train["item_id"].isin(eligible_set)]
    test = raw_test.loc[raw_test["item_id"].isin(eligible_set)]

    item_to_index = {item_id: index for index, item_id in enumerate(eligible_item_ids)}
    catalog = catalog.set_index("item_id").loc[eligible_item_ids].reset_index()
    feature_matrix = _unit_rows(catalog[data.feature_columns].to_numpy(dtype=float))

    item_counts = train.groupby("item_id", observed=True).size().reindex(eligible_item_ids, fill_value=0).to_numpy(dtype=int)
    popularity = (
        train.groupby("item_id", observed=True)["event_weight"]
        .sum()
        .reindex(eligible_item_ids, fill_value=0.0)
        .to_numpy(dtype=float)
    )
    cold_items = {item for item, count in zip(eligible_item_ids, item_counts, strict=True) if count <= config.cold_item_max_events}

    all_train_users = sorted(train["user_id"].unique())
    train_user_to_index = {user: index for index, user in enumerate(all_train_users)}
    aggregated = train.groupby(["user_id", "item_id"], observed=True)["event_weight"].sum().reset_index()
    rows = aggregated["user_id"].map(train_user_to_index).to_numpy(dtype=int)
    columns = aggregated["item_id"].map(item_to_index).to_numpy(dtype=int)
    values = aggregated["event_weight"].to_numpy(dtype=float)
    user_item = sparse.csr_matrix((values, (rows, columns)), shape=(len(all_train_users), len(eligible_item_ids)))
    gram = (user_item.T @ user_item).toarray().astype(float)
    norms = np.sqrt(np.diag(gram))
    denominator = np.outer(norms, norms)
    item_similarity = np.divide(gram, denominator, out=np.zeros_like(gram), where=denominator > 0)
    np.fill_diagonal(item_similarity, 0.0)

    history_counts = train.groupby("user_id", observed=True)["item_id"].nunique()
    train_items_by_user = train.groupby("user_id", observed=True)["item_id"].agg(lambda values: set(values.astype(str)))
    test_items_by_user = test.groupby("user_id", observed=True)["item_id"].agg(lambda values: set(values.astype(str)))
    # Repeat interactions are excluded from relevance because previously seen
    # items are excluded from the candidate set; users whose test window only
    # repeats their pre-cutoff items are not evaluable in this fold.
    test_relevance = {
        user: items - train_items_by_user.get(user, set()) for user, items in test_items_by_user.items()
    }
    eligible_users = sorted(
        user
        for user in history_counts[history_counts >= config.min_train_events].index
        if test_relevance.get(user)
    )
    subgroup_by_user = events.drop_duplicates("user_id").set_index("user_id")["subgroup"]
    history = aggregated.groupby("user_id", observed=True)

    recommendation_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    fallback_counts = {policy: 0 for policy in POLICIES}

    smoothing = 0.5
    probability = (item_counts + smoothing) / (item_counts.sum() + smoothing * len(item_counts))
    novelty = -np.log2(probability)

    for user_id in eligible_users:
        user_history = history.get_group(user_id)
        history_indices = user_history["item_id"].map(item_to_index).to_numpy(dtype=int)
        history_weights = user_history["event_weight"].to_numpy(dtype=float)
        seen = set(history_indices.tolist())
        candidates = np.array([index for index in range(len(eligible_item_ids)) if index not in seen], dtype=int)
        if not len(candidates):
            continue
        policy_scores, fallbacks = _score_catalog(
            history_indices,
            history_weights,
            popularity,
            feature_matrix,
            item_similarity,
            candidates,
            config,
        )
        relevant = test_relevance[user_id]
        cold_relevant = relevant.intersection(cold_items)
        for policy in POLICIES:
            scores = policy_scores[policy]
            ordered = sorted(candidates.tolist(), key=lambda index: (-float(scores[index]), eligible_item_ids[index]))
            top_indices = ordered[: config.k]
            recommended = [eligible_item_ids[index] for index in top_indices]
            hits = len(set(recommended).intersection(relevant))
            cold_hits = len(set(recommended).intersection(cold_relevant))
            fallback_counts[policy] += int(fallbacks[policy])
            metric_rows.append(
                {
                    "fold": fold.fold,
                    "policy": policy,
                    "user_id": user_id,
                    "subgroup": subgroup_by_user[user_id],
                    "n_train_items": int(history_counts[user_id]),
                    "n_relevant_items": len(relevant),
                    "n_cold_relevant_items": len(cold_relevant),
                    "recall_at_k": hits / len(relevant),
                    "ndcg_at_k": _ndcg(recommended, relevant, config.k),
                    "cold_item_recall_at_k": cold_hits / len(cold_relevant) if cold_relevant else np.nan,
                    "cold_user": bool(history_counts[user_id] <= config.cold_user_max_events),
                    "fallback_used": bool(fallbacks[policy]),
                }
            )
            for rank, item_index in enumerate(top_indices, start=1):
                recommendation_rows.append(
                    {
                        "fold": fold.fold,
                        "policy": policy,
                        "user_id": user_id,
                        "item_id": eligible_item_ids[item_index],
                        "rank": rank,
                        "score": float(scores[item_index]),
                        "novelty_bits": float(novelty[item_index]),
                        "cold_item": eligible_item_ids[item_index] in cold_items,
                    }
                )

    recommendations = pd.DataFrame(recommendation_rows)
    user_metrics = pd.DataFrame(metric_rows)
    return FoldOutput(
        recommendations=recommendations,
        user_metrics=user_metrics,
        diagnostics={
            "fold": fold.fold,
            "train_end": fold.train_end.isoformat(),
            "test_end": fold.test_end.isoformat(),
            "training_events": len(train),
            "test_events": len(test),
            "future_unavailable_test_events_excluded": len(raw_test) - len(test),
            "eligible_catalog_items": len(eligible_item_ids),
            "eligible_users": len(eligible_users),
            "cold_catalog_items": len(cold_items),
            **{f"{policy.lower().replace('-', '_').replace(' ', '_')}_fallbacks": count for policy, count in fallback_counts.items()},
        },
    )
