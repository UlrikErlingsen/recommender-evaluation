"""Offline recommendation-policy evaluation and uncertainty summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import count

import numpy as np
import pandas as pd
from scipy import stats

from .design import EvaluationConfig, ValidatedData, make_temporal_folds
from .errors import DataProblem
from .models import POLICIES, evaluate_fold


@dataclass
class EvaluationResult:
    config: EvaluationConfig
    folds: pd.DataFrame
    summaries: pd.DataFrame
    contrasts: pd.DataFrame
    fold_metrics: pd.DataFrame
    subgroup_metrics: pd.DataFrame
    subgroup_gaps: pd.DataFrame
    user_metrics: pd.DataFrame
    recommendations: pd.DataFrame
    diagnostics: pd.DataFrame
    warnings: list[str]


def _bootstrap_user_mean_ci(frame: pd.DataFrame, column: str, repetitions: int, seed: int) -> tuple[float, float, float]:
    values = frame.groupby("user_id", observed=True)[column].mean().dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    estimate = float(values.mean())
    if len(values) == 1:
        return estimate, np.nan, np.nan
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(repetitions, len(values)), replace=True).mean(axis=1)
    lower, upper = np.quantile(draws, [0.025, 0.975])
    return estimate, float(lower), float(upper)


def _exposure_metrics(recommendations: pd.DataFrame, catalog_size: int) -> dict[str, float]:
    if recommendations.empty or catalog_size <= 0:
        return {"coverage": np.nan, "novelty_bits": np.nan, "concentration_hhi": np.nan, "top_10_share": np.nan}
    counts = recommendations["item_id"].value_counts()
    shares = counts / counts.sum()
    top_n = min(10, len(counts))
    return {
        "coverage": recommendations["item_id"].nunique() / catalog_size,
        "novelty_bits": float(recommendations["novelty_bits"].mean()),
        "concentration_hhi": float(np.square(shares).sum()),
        "top_10_share": float(shares.nlargest(top_n).sum()),
    }


def _bh_adjust(p_values: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=p_values.index, dtype=float)
    valid = p_values.dropna().sort_values()
    if valid.empty:
        return result
    n = len(valid)
    adjusted = valid.to_numpy(dtype=float) * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result.loc[valid.index] = np.minimum(adjusted, 1.0)
    return result


def _summarize(
    user_metrics: pd.DataFrame,
    recommendations: pd.DataFrame,
    diagnostics: pd.DataFrame,
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fold_rows: list[dict[str, object]] = []
    for (fold, policy), group in user_metrics.groupby(["fold", "policy"], observed=True):
        recs = recommendations.loc[(recommendations["fold"] == fold) & (recommendations["policy"] == policy)]
        catalog_size = int(diagnostics.loc[diagnostics["fold"] == fold, "eligible_catalog_items"].iloc[0])
        exposure = _exposure_metrics(recs, catalog_size)
        cold_users = group.loc[group["cold_user"]]
        fold_rows.append(
            {
                "fold": fold,
                "policy": policy,
                "users": group["user_id"].nunique(),
                "recall_at_k": group["recall_at_k"].mean(),
                "ndcg_at_k": group["ndcg_at_k"].mean(),
                "cold_user_recall_at_k": cold_users["recall_at_k"].mean(),
                "cold_item_recall_at_k": group["cold_item_recall_at_k"].mean(),
                "fallback_rate": group["fallback_used"].mean(),
                **exposure,
            }
        )
    fold_metrics = pd.DataFrame(fold_rows)

    summary_rows: list[dict[str, object]] = []
    seed_counter = count(20260716)
    for policy in POLICIES:
        group = user_metrics.loc[user_metrics["policy"] == policy]
        policy_folds = fold_metrics.loc[fold_metrics["policy"] == policy]
        recall, recall_low, recall_high = _bootstrap_user_mean_ci(
            group, "recall_at_k", config.bootstrap_repetitions, next(seed_counter)
        )
        ndcg, ndcg_low, ndcg_high = _bootstrap_user_mean_ci(
            group, "ndcg_at_k", config.bootstrap_repetitions, next(seed_counter)
        )
        cold_users = group.loc[group["cold_user"]]
        summary_rows.append(
            {
                "policy": policy,
                "users": group["user_id"].nunique(),
                "user_fold_evaluations": len(group),
                "recall_at_k": recall,
                "recall_ci_low": recall_low,
                "recall_ci_high": recall_high,
                "ndcg_at_k": ndcg,
                "ndcg_ci_low": ndcg_low,
                "ndcg_ci_high": ndcg_high,
                "coverage": policy_folds["coverage"].mean(),
                "novelty_bits": policy_folds["novelty_bits"].mean(),
                "concentration_hhi": policy_folds["concentration_hhi"].mean(),
                "top_10_share": policy_folds["top_10_share"].mean(),
                "cold_user_recall_at_k": cold_users["recall_at_k"].mean(),
                "cold_item_recall_at_k": group["cold_item_recall_at_k"].mean(),
                "fallback_rate": group["fallback_used"].mean(),
            }
        )
    return pd.DataFrame(summary_rows), fold_metrics


def _contrasts(user_metrics: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    reference = config.reference_policy
    for policy in POLICIES:
        if policy == reference:
            continue
        for metric in ("recall_at_k", "ndcg_at_k"):
            pivot = user_metrics.pivot_table(index=["user_id", "fold"], columns="policy", values=metric, aggfunc="mean")
            paired = pivot[[reference, policy]].dropna()
            by_user = (paired[policy] - paired[reference]).groupby("user_id").mean().dropna()
            if len(by_user) < 2:
                estimate = lower = upper = p_value = np.nan
            else:
                estimate = float(by_user.mean())
                standard_error = float(stats.sem(by_user.to_numpy(dtype=float)))
                critical = float(stats.t.ppf(0.975, len(by_user) - 1))
                lower = estimate - critical * standard_error
                upper = estimate + critical * standard_error
                p_value = float(stats.ttest_1samp(by_user.to_numpy(dtype=float), popmean=0.0).pvalue)
            rows.append(
                {
                    "reference_policy": reference,
                    "candidate_policy": policy,
                    "metric": metric,
                    "paired_users": len(by_user),
                    "difference": estimate,
                    "ci_low": lower,
                    "ci_high": upper,
                    "p_value": p_value,
                }
            )
    contrasts = pd.DataFrame(rows)
    contrasts["q_value"] = _bh_adjust(contrasts["p_value"])
    contrasts["offline_evidence"] = np.select(
        [
            (contrasts["ci_low"] > 0) & (contrasts["q_value"] <= 0.05),
            (contrasts["ci_high"] < 0) & (contrasts["q_value"] <= 0.05),
        ],
        ["Clear offline increase", "Clear offline decrease"],
        default="Uncertain offline difference",
    )
    return contrasts


def _subgroups(user_metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for (policy, subgroup), group in user_metrics.groupby(["policy", "subgroup"], observed=True):
        user_level = group.groupby("user_id", observed=True)[["recall_at_k", "ndcg_at_k"]].mean()
        rows.append(
            {
                "policy": policy,
                "subgroup": subgroup,
                "users": len(user_level),
                "user_fold_evaluations": len(group),
                "recall_at_k": user_level["recall_at_k"].mean(),
                "ndcg_at_k": user_level["ndcg_at_k"].mean(),
                "cold_user_share": group.groupby("user_id", observed=True)["cold_user"].max().mean(),
                "cold_item_recall_at_k": group.groupby("user_id", observed=True)["cold_item_recall_at_k"].mean().mean(),
            }
        )
    subgroup_metrics = pd.DataFrame(rows)
    gap_rows: list[dict[str, object]] = []
    for policy, group in subgroup_metrics.groupby("policy", observed=True):
        for metric in ("recall_at_k", "ndcg_at_k"):
            valid = group.dropna(subset=[metric])
            if valid.empty:
                continue
            lowest = valid.loc[valid[metric].idxmin()]
            highest = valid.loc[valid[metric].idxmax()]
            gap_rows.append(
                {
                    "policy": policy,
                    "metric": metric,
                    "lowest_subgroup": lowest["subgroup"],
                    "highest_subgroup": highest["subgroup"],
                    "max_minus_min_gap": highest[metric] - lowest[metric],
                    "lowest_value": lowest[metric],
                    "highest_value": highest[metric],
                }
            )
    return subgroup_metrics, pd.DataFrame(gap_rows)


def evaluate_policies(data: ValidatedData, config: EvaluationConfig | None = None) -> EvaluationResult:
    """Evaluate all declared policies without claiming an online treatment effect."""

    config = config or EvaluationConfig()
    folds = make_temporal_folds(data.events, config)
    outputs = [evaluate_fold(data, fold, config) for fold in folds]
    user_frames = [output.user_metrics for output in outputs if not output.user_metrics.empty]
    rec_frames = [output.recommendations for output in outputs if not output.recommendations.empty]
    if not user_frames or not rec_frames:
        raise DataProblem(
            "No fold has users with enough pre-cutoff history and eligible post-cutoff interactions. Reduce the minimum history or use more data."
        )
    user_metrics = pd.concat(user_frames, ignore_index=True)
    recommendations = pd.concat(rec_frames, ignore_index=True)
    diagnostics = pd.DataFrame([output.diagnostics for output in outputs])
    summaries, fold_metrics = _summarize(user_metrics, recommendations, diagnostics, config)
    contrasts = _contrasts(user_metrics, config)
    subgroup_metrics, subgroup_gaps = _subgroups(user_metrics)
    fold_frame = pd.DataFrame(
        [
            {"fold": fold.fold, "train_before": fold.train_end.isoformat(), "test_before": fold.test_end.isoformat()}
            for fold in folds
        ]
    )
    warnings = list(data.warnings)
    warnings.extend(
        [
            "Recall and NDCG replay observed interactions, not complete relevance judgments; exposure and selection bias remain.",
            "Offline policy differences do not establish commercial lift, user welfare, or causality. Test a final policy in ExperimentSignal.",
            "Subgroup gaps are descriptive diagnostics, not automatic findings of fairness, discrimination, or harm.",
            "Confidence intervals resample users and remain approximate when users or items are dependent.",
            f"Hybrid weights for this run: {asdict(config)['hybrid_popularity_weight']:.2f} popularity, "
            f"{asdict(config)['hybrid_content_weight']:.2f} content, and "
            f"{asdict(config)['hybrid_collaborative_weight']:.2f} collaborative. Repeatedly changing weights after viewing "
            "holdout results turns the holdout into tuning data.",
        ]
    )
    return EvaluationResult(
        config=config,
        folds=fold_frame,
        summaries=summaries,
        contrasts=contrasts,
        fold_metrics=fold_metrics,
        subgroup_metrics=subgroup_metrics,
        subgroup_gaps=subgroup_gaps,
        user_metrics=user_metrics,
        recommendations=recommendations,
        diagnostics=diagnostics,
        warnings=warnings,
    )
