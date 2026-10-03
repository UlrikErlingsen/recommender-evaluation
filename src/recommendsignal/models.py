"""Transparent baseline recommendation policies."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os

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


def _ndcg(recommended: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return np.nan
    dcg = sum(1.0 / np.log2(rank + 2.0) for rank, item in enumerate(recommended[:k]) if item in relevant)
    ideal_length = min(len(relevant), k)
    ideal = sum(1.0 / np.log2(rank + 2.0) for rank in range(ideal_length))
    return float(dcg / ideal) if ideal else np.nan


# Users are scored in batches whose dense score matrices hold about this many cells, so memory stays bounded
# whatever the number of users or catalog items.
BATCH_CELLS = 1_000_000
# Threads used to score user batches (results are identical for any number of threads).
SCORING_THREADS = max(1, min(8, (os.cpu_count() or 2) - 1))
# Above this many catalog items the item-item similarity is normalized in place to avoid extra dense copies.
IN_PLACE_SIMILARITY_ITEMS = 5_000


def _batch_relative_rank(scores: np.ndarray, seen: np.ndarray, candidate_counts: np.ndarray) -> np.ndarray:
    """Per user, stable ascending ranks of the candidate (unseen) items' scores mapped onto [0, 1].

    Ties keep catalog order; one candidate gets rank 1. Seen items get 0 and are never recommended.
    """
    order = np.argsort(np.where(seen, np.inf, scores), axis=1, kind="stable")
    width = scores.shape[1]
    positions = np.broadcast_to(np.arange(width, dtype=float), scores.shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        step = 1.0 / (candidate_counts - 1)
        values = positions * step[:, None]  # np.linspace(0, 1, n) computes j * (1 / (n - 1)) and ends exactly at 1
    last = (candidate_counts - 1)[:, None]
    values = np.where(np.arange(width)[None, :] == last, 1.0, values)
    values = np.where(candidate_counts[:, None] <= 1, 1.0, values)
    ranks = np.zeros_like(scores, dtype=float)
    np.put_along_axis(ranks, order, values, axis=1)
    return np.where(seen, 0.0, ranks)


def _batch_popularity_rank(
    global_order: np.ndarray, seen: np.ndarray, candidate_counts: np.ndarray
) -> np.ndarray:
    """``_batch_relative_rank`` for scores shared by every user (popularity), without a sort per user.

    A user's candidates keep the shared stable order, so an item's rank is its shared position minus the number
    of that user's seen items placed before it.
    """
    width = seen.shape[1]
    seen_in_order = seen[:, global_order]
    position = np.arange(width)[None, :] - np.cumsum(seen_in_order, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        step = 1.0 / (candidate_counts - 1)
        values = position * step[:, None]
    values = np.where(position == (candidate_counts - 1)[:, None], 1.0, values)
    values = np.where(candidate_counts[:, None] <= 1, 1.0, values)
    ranks = np.zeros(seen.shape, dtype=float)
    ranks[:, global_order] = values
    return np.where(seen, 0.0, ranks)


def _top_k(scores: np.ndarray, seen: np.ndarray, k: int) -> np.ndarray:
    """Per row, the indices of the k highest-scoring unseen items, ties by index, as a stable full sort would give.

    Partial selection keeps this linear in the catalog size; rows with fewer than k unseen items are padded with
    seen items at the end (callers mask them with the slate length).
    """
    key = np.where(seen, np.inf, -scores)
    width = key.shape[1]
    if k >= width:
        return np.argsort(key, axis=1, kind="stable")[:, :k]
    threshold = np.partition(key, k - 1, axis=1)[:, k - 1 : k]
    better = key < threshold
    room = k - better.sum(axis=1, keepdims=True)
    tied = key == threshold
    chosen = better | (tied & (np.cumsum(tied, axis=1) <= room))
    columns = np.nonzero(chosen)[1].reshape(-1, k)  # exactly k per row, ascending within each row
    order = np.argsort(np.take_along_axis(key, columns, axis=1), axis=1, kind="stable")
    return np.take_along_axis(columns, order, axis=1)


def _masked_ptp(scores: np.ndarray, seen: np.ndarray) -> np.ndarray:
    high = np.where(seen, -np.inf, scores).max(axis=1)
    low = np.where(seen, np.inf, scores).min(axis=1)
    return high - low


def evaluate_fold(data: ValidatedData, fold: TemporalFold, config: EvaluationConfig) -> FoldOutput:
    """Fit four baselines before a cutoff and replay the following window.

    Users are scored in batches with matrix operations; each user's slate, ranks and metrics are the same as
    scoring that user alone against the full eligible catalog.
    """

    events = data.events
    train = events.loc[events["timestamp"] < fold.train_end]
    raw_test = events.loc[(events["timestamp"] >= fold.train_end) & (events["timestamp"] < fold.test_end)]
    catalog = data.items.loc[data.items["available_at"] <= fold.train_end].copy()
    eligible_item_ids = sorted(catalog["item_id"].astype(str))
    eligible_set = set(eligible_item_ids)
    train = train.loc[train["item_id"].isin(eligible_set)]
    test = raw_test.loc[raw_test["item_id"].isin(eligible_set)]
    n_items = len(eligible_item_ids)

    item_to_index = {item_id: index for index, item_id in enumerate(eligible_item_ids)}
    item_id_array = np.asarray(eligible_item_ids, dtype=object)
    catalog = catalog.set_index("item_id").loc[eligible_item_ids].reset_index()
    feature_matrix = _unit_rows(catalog[data.feature_columns].to_numpy(dtype=float))

    item_counts = train.groupby("item_id", observed=True).size().reindex(eligible_item_ids, fill_value=0).to_numpy(dtype=int)
    popularity = (
        train.groupby("item_id", observed=True)["event_weight"]
        .sum()
        .reindex(eligible_item_ids, fill_value=0.0)
        .to_numpy(dtype=float)
    )
    cold_mask = item_counts <= config.cold_item_max_events
    cold_items_count = int(cold_mask.sum())

    all_train_users = sorted(train["user_id"].unique())
    train_user_to_index = {user: index for index, user in enumerate(all_train_users)}
    aggregated = train.groupby(["user_id", "item_id"], observed=True)["event_weight"].sum().reset_index()
    rows = aggregated["user_id"].map(train_user_to_index).to_numpy(dtype=int)
    columns = aggregated["item_id"].map(item_to_index).to_numpy(dtype=int)
    values = aggregated["event_weight"].to_numpy(dtype=float)
    user_item = sparse.csr_matrix((values, (rows, columns)), shape=(len(all_train_users), n_items))
    user_item.sort_indices()
    gram = (user_item.T @ user_item).toarray().astype(float)
    norms = np.sqrt(np.diag(gram))
    if n_items <= IN_PLACE_SIMILARITY_ITEMS:
        denominator = np.outer(norms, norms)
        item_similarity = np.divide(gram, denominator, out=np.zeros_like(gram), where=denominator > 0)
        del denominator
    else:
        # Large catalogs: normalize the one dense matrix in place instead of allocating two more of the same size.
        safe = np.where(norms > 0, norms, 1.0)
        item_similarity = gram
        item_similarity /= safe[:, None]
        item_similarity /= safe[None, :]
        item_similarity[norms == 0, :] = 0.0
        item_similarity[:, norms == 0] = 0.0
    del gram
    np.fill_diagonal(item_similarity, 0.0)

    history_counts = (
        np.diff(user_item.indptr) if len(all_train_users) else np.zeros(0, dtype=int)
    )  # unique pre-cutoff items per user (rows hold one entry per user-item pair)
    test_pairs = test[["user_id", "item_id"]].drop_duplicates()
    test_pairs = test_pairs.loc[test_pairs["user_id"].isin(train_user_to_index)]
    test_rows = test_pairs["user_id"].map(train_user_to_index).to_numpy(dtype=int)
    test_columns = test_pairs["item_id"].map(item_to_index).to_numpy(dtype=int)
    relevance = sparse.csr_matrix(
        (np.ones(len(test_rows)), (test_rows, test_columns)), shape=(len(all_train_users), n_items)
    )
    # Repeat interactions are excluded from relevance because previously seen
    # items are excluded from the candidate set; users whose test window only
    # repeats their pre-cutoff items are not evaluable in this fold.
    relevance = relevance - relevance.multiply(user_item > 0)
    relevance.eliminate_zeros()
    relevant_counts = np.diff(relevance.indptr)
    eligible_rows = np.flatnonzero((history_counts >= config.min_train_events) & (relevant_counts > 0))
    subgroup_by_user = events.drop_duplicates("user_id").set_index("user_id")["subgroup"]
    train_user_array = np.asarray(all_train_users, dtype=object)

    smoothing = 0.5
    probability = (item_counts + smoothing) / (item_counts.sum() + smoothing * len(item_counts))
    novelty = -np.log2(probability)
    pop_scores = np.log1p(popularity)
    popularity_order = np.argsort(pop_scores, kind="stable")
    discounts = 1.0 / np.log2(np.arange(config.k) + 2.0)
    cumulative_discounts = np.cumsum(discounts)
    weights = (config.hybrid_popularity_weight, config.hybrid_content_weight, config.hybrid_collaborative_weight)

    metric_parts: list[pd.DataFrame] = []
    recommendation_parts: list[pd.DataFrame] = []
    fallback_counts = {policy: 0 for policy in POLICIES}
    batch_size = max(1, BATCH_CELLS // max(n_items, 1))
    def score_batch(batch: np.ndarray):
        local_fallbacks = {policy: 0 for policy in POLICIES}
        history = user_item[batch]
        history.sort_indices()
        seen = history.toarray() > 0
        candidate_counts = n_items - seen.sum(axis=1)
        keep = candidate_counts > 0
        if not keep.all():
            batch, history, seen, candidate_counts = batch[keep], history[keep], seen[keep], candidate_counts[keep]
        if not len(batch):
            return None
        size = len(batch)
        # Content and collaborative scores use the same per-user products as scoring one user at a time, so
        # near-ties break exactly as they always have; ranking, slates and metrics below run on the whole batch.
        content = np.zeros((size, n_items))
        collaborative = np.empty((size, n_items))
        for row in range(size):
            history_indices = history.indices[history.indptr[row] : history.indptr[row + 1]]
            history_weights = history.data[history.indptr[row] : history.indptr[row + 1]]
            profile = (feature_matrix[history_indices] * history_weights[:, None]).sum(axis=0)
            profile_norm = np.linalg.norm(profile)
            if profile_norm > 0:
                content[row] = feature_matrix @ (profile / profile_norm)
            collaborative[row] = item_similarity[:, history_indices] @ history_weights
        popularity_rows = np.broadcast_to(pop_scores, (size, n_items))
        content_fallback = _masked_ptp(content, seen) <= 1e-12
        collaborative_fallback = _masked_ptp(collaborative, seen) <= 1e-12
        content[content_fallback] = pop_scores
        collaborative[collaborative_fallback] = pop_scores
        hybrid = (
            weights[0] * _batch_popularity_rank(popularity_order, seen, candidate_counts)
            + weights[1] * _batch_relative_rank(content, seen, candidate_counts)
            + weights[2] * _batch_relative_rank(collaborative, seen, candidate_counts)
        )
        fallbacks = {
            "Popularity": np.zeros(size, dtype=bool),
            "Content-based": content_fallback,
            "Collaborative": collaborative_fallback,
            "Hybrid": content_fallback | collaborative_fallback,
        }
        policy_scores = {"Popularity": popularity_rows, "Content-based": content, "Collaborative": collaborative, "Hybrid": hybrid}

        relevant = relevance[batch].toarray() > 0
        n_relevant = relevant.sum(axis=1)
        cold_relevant = relevant & cold_mask[None, :]
        n_cold_relevant = cold_relevant.sum(axis=1)
        width = min(config.k, n_items)
        slate_length = np.minimum(candidate_counts, config.k)
        in_slate = np.arange(width)[None, :] < slate_length[:, None]
        users = train_user_array[batch]
        user_history = history_counts[batch]
        subgroups = subgroup_by_user.reindex(users).to_numpy()
        ideal = cumulative_discounts[np.minimum(n_relevant, config.k) - 1]

        policy_metrics: list[dict[str, np.ndarray]] = []
        policy_slates: list[tuple[np.ndarray, np.ndarray]] = []
        for policy in POLICIES:
            scores = policy_scores[policy]
            # Highest score first, ties by item ID (the catalog index order); seen items sort last.
            order = _top_k(scores, seen, width)
            hit = np.take_along_axis(relevant, order, axis=1) & in_slate
            cold_hit = np.take_along_axis(cold_relevant, order, axis=1) & in_slate
            dcg = np.cumsum(hit * discounts[None, :width], axis=1)[:, -1]
            local_fallbacks[policy] += int(fallbacks[policy].sum())
            with np.errstate(divide="ignore", invalid="ignore"):
                cold_recall = np.where(n_cold_relevant > 0, cold_hit.sum(axis=1) / n_cold_relevant, np.nan)
            policy_metrics.append(
                {
                    "recall_at_k": hit.sum(axis=1) / n_relevant,
                    "ndcg_at_k": dcg / ideal,
                    "cold_item_recall_at_k": cold_recall,
                    "fallback_used": fallbacks[policy],
                }
            )
            policy_slates.append((order, np.take_along_axis(scores, order, axis=1)))

        # Rows ordered user by user, then policy by policy (then rank), as a per-user loop would produce them.
        n_policies = len(POLICIES)
        metrics_frame = (
            pd.DataFrame(
                {
                    "fold": fold.fold,
                    "policy": np.tile(np.asarray(POLICIES, dtype=object), size),
                    "user_id": np.repeat(users, n_policies),
                    "subgroup": np.repeat(subgroups, n_policies),
                    "n_train_items": np.repeat(user_history, n_policies).astype(int),
                    "n_relevant_items": np.repeat(n_relevant, n_policies).astype(int),
                    "n_cold_relevant_items": np.repeat(n_cold_relevant, n_policies).astype(int),
                    **{
                        name: np.stack([metrics[name] for metrics in policy_metrics], axis=1).ravel()
                        for name in ("recall_at_k", "ndcg_at_k", "cold_item_recall_at_k")
                    },
                    "cold_user": np.repeat(user_history <= config.cold_user_max_events, n_policies),
                    "fallback_used": np.stack([metrics["fallback_used"] for metrics in policy_metrics], axis=1).ravel(),
                }
            )
        )
        orders = np.stack([slate[0] for slate in policy_slates], axis=1)  # users × policies × k
        slate_scores = np.stack([slate[1] for slate in policy_slates], axis=1)
        mask = np.broadcast_to(in_slate[:, None, :], orders.shape).ravel()
        flat_items = orders.ravel()[mask]
        slates_frame = (
            pd.DataFrame(
                {
                    "fold": fold.fold,
                    "policy": np.broadcast_to(
                        np.asarray(POLICIES, dtype=object)[None, :, None], orders.shape
                    ).ravel()[mask],
                    "user_id": np.broadcast_to(users[:, None, None], orders.shape).ravel()[mask],
                    "item_id": item_id_array[flat_items],
                    "rank": np.broadcast_to(np.arange(1, width + 1)[None, None, :], orders.shape).ravel()[mask],
                    "score": slate_scores.ravel()[mask].astype(float),
                    "novelty_bits": novelty[flat_items].astype(float),
                    "cold_item": cold_mask[flat_items],
                }
            )
        )
        return metrics_frame, slates_frame, local_fallbacks

    batches = [eligible_rows[start : start + batch_size] for start in range(0, len(eligible_rows), batch_size)]
    workers = min(SCORING_THREADS, len(batches))
    if workers > 1:
        # NumPy releases the GIL in sorting and array arithmetic, so batches score in parallel threads.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outputs = list(pool.map(score_batch, batches))
    else:
        outputs = [score_batch(batch) for batch in batches]
    for output in outputs:
        if output is None:
            continue
        metrics_frame, slates_frame, local_fallbacks = output
        metric_parts.append(metrics_frame)
        recommendation_parts.append(slates_frame)
        for policy, count in local_fallbacks.items():
            fallback_counts[policy] += count
    del outputs

    metric_columns = [
        "fold", "policy", "user_id", "subgroup", "n_train_items", "n_relevant_items", "n_cold_relevant_items",
        "recall_at_k", "ndcg_at_k", "cold_item_recall_at_k", "cold_user", "fallback_used",
    ]
    recommendation_columns = ["fold", "policy", "user_id", "item_id", "rank", "score", "novelty_bits", "cold_item"]
    recommendations = (
        pd.concat(recommendation_parts, ignore_index=True) if recommendation_parts else pd.DataFrame()
    )
    user_metrics = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    recommendation_parts.clear()
    metric_parts.clear()
    if not user_metrics.empty:
        user_metrics = user_metrics[metric_columns]
        recommendations = recommendations[recommendation_columns]
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
            "eligible_catalog_items": n_items,
            "eligible_users": len(eligible_rows),
            "cold_catalog_items": cold_items_count,
            **{f"{policy.lower().replace('-', '_').replace(' ', '_')}_fallbacks": count for policy, count in fallback_counts.items()},
        },
    )
