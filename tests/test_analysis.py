from __future__ import annotations

from recommendsignal.models import POLICIES


def test_policy_summary_contains_four_separate_policies(result) -> None:
    assert set(result.summaries["policy"]) == set(POLICIES)
    assert "universal_score" not in result.summaries.columns
    assert result.summaries["coverage"].between(0, 1).all()
    assert result.summaries["concentration_hhi"].between(0, 1).all()


def test_recall_and_ndcg_intervals_are_ordered(result) -> None:
    assert (result.summaries["recall_ci_low"] <= result.summaries["recall_at_k"]).all()
    assert (result.summaries["recall_at_k"] <= result.summaries["recall_ci_high"]).all()
    assert (result.summaries["ndcg_ci_low"] <= result.summaries["ndcg_at_k"]).all()
    assert (result.summaries["ndcg_at_k"] <= result.summaries["ndcg_ci_high"]).all()


def test_paired_contrasts_cover_three_candidates_and_two_metrics(result) -> None:
    assert len(result.contrasts) == 6
    assert result.contrasts["paired_users"].gt(1).all()
    assert result.contrasts["q_value"].between(0, 1).all()
    assert set(result.contrasts["offline_evidence"]).issubset(
        {"Clear offline increase", "Clear offline decrease", "Uncertain offline difference"}
    )


def test_fold_metrics_include_distributional_evidence(result) -> None:
    assert len(result.fold_metrics) == result.config.n_folds * 4
    assert {"coverage", "novelty_bits", "concentration_hhi", "top_10_share"}.issubset(result.fold_metrics.columns)


def test_subgroup_tables_remain_policy_specific(result) -> None:
    assert set(result.subgroup_metrics["policy"]) == set(POLICIES)
    assert result.subgroup_metrics["subgroup"].nunique() == 3
    assert len(result.subgroup_gaps) == 8


def test_warnings_preserve_offline_causal_boundary(result) -> None:
    warnings = " ".join(result.warnings)
    assert "do not establish commercial lift" in warnings
    assert "ExperimentSignal" in warnings
    assert "descriptive diagnostics" in warnings
