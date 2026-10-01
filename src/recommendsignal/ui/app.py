"""Recommend Signal Streamlit UI.

Everything that draws the app runs inside ``render()`` (or the functions it calls), so it runs on every rerun,
both in the standalone ``app.py`` and inside Signal Hub. Module-level code here only defines constants and
functions. ``render()`` never calls ``st.set_page_config`` or ``st.navigation``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import traceback
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from recommendsignal import DataProblem, EvaluationConfig, __version__, evaluate_policies, validate_inputs
from recommendsignal.design import audit_data, make_temporal_folds
from recommendsignal.examples import (
    make_catalog_template,
    make_demo_catalog,
    make_demo_events,
    make_event_template,
)
from recommendsignal.io import build_evidence_workbook, dataframe_csv_bytes, read_table
from recommendsignal.ui import signal_theme as sig


NS = "recommend"


def k(name: str) -> str:
    """Namespace a session-state or widget key with the app slug, so apps can share one Hub session."""
    return f"{NS}:{name}"


SIDEBAR_TAGLINE = "Compare policies before the live test."
MASTHEAD_KICKER = "REPLAY → COMPARE → CHALLENGE"
MASTHEAD_PROMISES = ["Local-first", "Named methods", "Portable evidence"]
FOOTER_LINE = "Offline policy evidence—not business lift"
NAME_NOTE = (
    "**Name status:** a basic screen found no obvious exact active software product, but that is not a trademark "
    "opinion or formal clearance."
)

PAGES = [
    "Welcome",
    "1 · Data & temporal contract",
    "2 · Offline leaderboard",
    "3 · Trade-offs & stability",
    "4 · Cold start & subgroups",
    "5 · Evidence pack",
    "Methods & boundaries",
]

DEMO_SOURCE = "Fictional demonstration"
UPLOAD_SOURCE = "Upload my files"
DEMO_LABEL = "Deterministic fictional demonstration"

HYBRID_PRESETS = {
    "Balanced": (0.25, 0.35, 0.40),
    "Collaborative-led": (0.20, 0.25, 0.55),
    "Content-led": (0.20, 0.55, 0.25),
}
POLICY_CHOICES = ["Popularity", "Content-based", "Collaborative", "Hybrid"]


@dataclass(frozen=True)
class SidebarChoices:
    """What the sidebar selected on this rerun: the page, the data source and the evaluation settings."""

    page: str
    source: str
    event_upload: Any
    item_upload: Any
    settings: dict[str, Any]


@st.cache_data(show_spinner=False)
def _demo() -> tuple[pd.DataFrame, pd.DataFrame]:
    return make_demo_events(), make_demo_catalog()


@st.cache_data(show_spinner="Running temporal policy evaluation…")
def _evaluate(events: pd.DataFrame, items: pd.DataFrame, config: EvaluationConfig):
    data = validate_inputs(events, items)
    return data, audit_data(data), evaluate_policies(data, config)


def _store(events: pd.DataFrame, items: pd.DataFrame, source_label: str) -> None:
    st.session_state[k("events")] = events
    st.session_state[k("items")] = items
    st.session_state[k("source_label")] = source_label


def _ensure_state() -> None:
    if k("events") not in st.session_state:
        _store(*_demo(), DEMO_LABEL)


def show_error(exc: Exception) -> None:
    """Render a useful error while keeping tracebacks opt-in."""
    if isinstance(exc, DataProblem):
        st.error(str(exc))
        return
    st.error(
        "Recommend Signal hit an unexpected problem while drawing this page. Check the inputs and settings, then "
        "try again."
    )
    if os.getenv("RECOMMENDSIGNAL_DEBUG") == "1":
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


def _load_data(choices: SidebarChoices) -> None:
    """Put the selected interaction log and item catalog into session state (the demo until both uploads exist)."""
    if choices.source == DEMO_SOURCE:
        _store(*_demo(), DEMO_LABEL)
        return
    if choices.event_upload is None or choices.item_upload is None:
        st.info("Upload both the interaction log and the item catalog. Until then, the fictional demonstration remains active.")
        _store(*_demo(), "Fictional demonstration while uploads are incomplete")
        return
    events = read_table(choices.event_upload.name, choices.event_upload.getvalue(), sheet_name="interactions")
    items = read_table(choices.item_upload.name, choices.item_upload.getvalue(), sheet_name="items")
    _store(events, items, "User-supplied local data")


def _settings() -> dict[str, Any]:
    """Draw the evaluation-contract controls (inside the sidebar) and return the EvaluationConfig arguments."""
    st.markdown("### Evaluation contract")
    depth = st.slider("Recommendation depth K", 5, 30, 10, 5, key=k("depth"))
    folds = st.slider("Temporal folds", 1, 4, 3, key=k("folds"))
    initial = st.slider("Initial training share", 0.50, 0.80, 0.60, 0.05, key=k("initial_share"))
    min_history = st.slider("Minimum pre-cutoff items", 1, 10, 3, key=k("min_history"))
    cold_user = st.slider("Cold-user history ceiling", min_history, 15, max(5, min_history), key=k("cold_user"))
    cold_item = st.slider("Cold-item event ceiling", 0, 10, 3, key=k("cold_item"))
    preset = st.selectbox("Declared hybrid mix", list(HYBRID_PRESETS), key=k("hybrid_preset"))
    reference = st.selectbox("Contrast reference", POLICY_CHOICES, key=k("reference"))
    pop_weight, content_weight, collaborative_weight = HYBRID_PRESETS[preset]
    st.caption(
        f"Hybrid: {pop_weight:.0%} popularity · {content_weight:.0%} content · {collaborative_weight:.0%} collaborative"
    )
    return {
        "k": depth,
        "n_folds": folds,
        "initial_train_fraction": initial,
        "min_train_events": min_history,
        "cold_user_max_events": cold_user,
        "cold_item_max_events": cold_item,
        "bootstrap_repetitions": 400,
        "hybrid_popularity_weight": pop_weight,
        "hybrid_content_weight": content_weight,
        "hybrid_collaborative_weight": collaborative_weight,
        "reference_policy": reference,
    }


def _percent(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.1%}"


def _summary_table(result) -> pd.DataFrame:
    table = result.summaries.copy()
    table = table.rename(
        columns={
            "policy": "Policy",
            "recall_at_k": f"Recall@{result.config.k}",
            "ndcg_at_k": f"NDCG@{result.config.k}",
            "coverage": "Coverage",
            "novelty_bits": "Novelty (bits)",
            "concentration_hhi": "Exposure HHI",
            "top_10_share": "Top-10 item share",
            "cold_user_recall_at_k": f"Cold-user Recall@{result.config.k}",
            "cold_item_recall_at_k": f"Cold-item Recall@{result.config.k}",
            "fallback_rate": "Fallback rate",
        }
    )
    columns = [
        "Policy",
        f"Recall@{result.config.k}",
        f"NDCG@{result.config.k}",
        "Coverage",
        "Novelty (bits)",
        "Exposure HHI",
        "Top-10 item share",
        f"Cold-user Recall@{result.config.k}",
        f"Cold-item Recall@{result.config.k}",
        "Fallback rate",
    ]
    return table[columns]


def page_welcome() -> None:
    sig.hero(
        NS,
        eyebrow="RECOMMENDATION POLICY EVIDENCE",
        title="Which recommender",
        em="earns the slot?",
        body=(
            "Compare four transparent recommendation policies under global temporal holdouts—ranking evidence, "
            "discovery, exposure concentration, cold start, and subgroup behavior without one magical recommendation "
            "score."
        ),
        pills=["Temporal holdouts", "Four transparent baselines", "Full eligible catalog", "No causal-lift claim"],
    )
    sig.note("warn", NAME_NOTE)
    sig.cards(
        [
            (
                "01 · REPLAY",
                "Global-time first",
                "Expanding training windows end before nonoverlapping test windows. Items unavailable at a cutoff "
                "cannot enter that fold's slate.",
            ),
            (
                "02 · COMPARE",
                "Four declared baselines",
                "Popularity, content-based, item-item collaborative, and a preweighted hybrid are evaluated against "
                "the same eligible users and catalog.",
            ),
            (
                "03 · CHALLENGE",
                "Evidence, not magic",
                "Ranking accuracy sits beside coverage, novelty, concentration, cold-start, and subgroup "
                "diagnostics—not inside one score.",
            ),
        ]
    )
    sig.note(
        "boundary",
        "**Decision boundary:** offline replay can reject weak ideas and expose trade-offs. It cannot show "
        "incremental sales, retention, satisfaction, or welfare. A final policy belongs in a randomized "
        "Experiment Signal test.",
    )
    st.markdown("### Workflow")
    st.markdown(
        "1. Audit interactions, features, availability, and temporal folds.\n"
        "2. Compare ranking evidence with uncertainty.\n"
        "3. Inspect discovery and exposure concentration.\n"
        "4. Audit cold-start and subgroup differences.\n"
        "5. Export the evidence pack and preregister an online experiment."
    )


def page_data(events: pd.DataFrame, items: pd.DataFrame, source_label: str, config: EvaluationConfig) -> None:
    sig.header("Step 1", "Data & temporal contract")
    st.caption(source_label)
    data = validate_inputs(events, items)
    audit = audit_data(data)
    folds = make_temporal_folds(data.events, config)
    col1, col2, col3, col4 = st.columns(4)
    values = dict(zip(audit.overview["measure"], audit.overview["value"], strict=True))
    col1.metric("Users", f"{int(values['Users']):,}")
    col2.metric("Events", f"{int(values['Events']):,}")
    col3.metric("Catalog items", f"{int(values['Catalog items']):,}")
    col4.metric("Content features", f"{int(values['Content features']):,}")

    st.markdown("### Expanding-window folds")
    fold_table = pd.DataFrame(
        [
            {
                "Fold": fold.fold,
                "Training data": f"timestamp < {fold.train_end.date()}",
                "Test window": f"{fold.train_end.date()} ≤ timestamp < {fold.test_end.date()}",
                "Catalog snapshot": f"available_at ≤ {fold.train_end.date()}",
            }
            for fold in folds
        ]
    )
    st.dataframe(fold_table, width="stretch", hide_index=True)
    left, right = st.columns(2)
    with left:
        st.markdown("### User subgroups")
        st.dataframe(audit.subgroup_counts, width="stretch", hide_index=True)
    with right:
        st.markdown("### Item availability")
        st.dataframe(audit.item_availability, width="stretch", hide_index=True)

    with st.expander("Input contract and warnings"):
        st.write(
            "Interactions require user_id, item_id, and timestamp. event_weight and subgroup are optional. "
            "The item catalog requires unique item_id, item_name, and at least one numeric feature_ column; available_at is strongly recommended."
        )
        for warning in audit.warnings:
            st.warning(warning)

    downloads = st.columns(2)
    downloads[0].download_button(
        "Download interaction template",
        dataframe_csv_bytes(make_event_template()),
        "recommendsignal-event-template.csv",
        "text/csv",
        key=k("download_event_template"),
    )
    downloads[1].download_button(
        "Download item template",
        dataframe_csv_bytes(make_catalog_template()),
        "recommendsignal-item-template.csv",
        "text/csv",
        key=k("download_item_template"),
    )


def page_leaderboard(result) -> None:
    sig.header(
        "Step 2",
        "Offline leaderboard",
        "Exact full-catalog replay at the selected K. Higher is better for Recall and NDCG.",
    )
    best_recall = result.summaries.loc[result.summaries["recall_at_k"].idxmax()]
    best_ndcg = result.summaries.loc[result.summaries["ndcg_at_k"].idxmax()]
    best_coverage = result.summaries.loc[result.summaries["coverage"].idxmax()]
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Highest offline Recall@{result.config.k}", _percent(best_recall["recall_at_k"]), best_recall["policy"])
    c2.metric(f"Highest offline NDCG@{result.config.k}", _percent(best_ndcg["ndcg_at_k"]), best_ndcg["policy"])
    c3.metric("Broadest catalog coverage", _percent(best_coverage["coverage"]), best_coverage["policy"])

    long = result.summaries.melt(
        id_vars="policy", value_vars=["recall_at_k", "ndcg_at_k"], var_name="metric", value_name="value"
    )
    long["metric"] = long["metric"].map(
        {"recall_at_k": f"Recall@{result.config.k}", "ndcg_at_k": f"NDCG@{result.config.k}"}
    )
    figure = px.bar(
        long,
        x="policy",
        y="value",
        color="metric",
        barmode="group",
        labels={"policy": "Policy", "value": "Macro user-level value", "metric": "Metric"},
        color_discrete_sequence=sig.colorway(NS),
        template=sig.template(NS),
    )
    figure.update_layout(yaxis_tickformat=".0%", legend_orientation="h", legend_y=1.12, margin=dict(t=35))
    sig.chart(NS, figure, key=k("leaderboard_chart"))
    st.dataframe(_summary_table(result), width="stretch", hide_index=True)

    st.markdown(f"### Paired contrasts against {result.config.reference_policy}")
    st.write(
        "Each difference is candidate minus reference on the same users, averaged across their available folds. "
        "Intervals are paired user-level t intervals; q-values use Benjamini–Hochberg adjustment across this table."
    )
    st.dataframe(result.contrasts, width="stretch", hide_index=True)
    st.warning("An offline increase is not a causal, commercial, or user-welfare lift.")


def page_tradeoffs(result) -> None:
    sig.header(
        "Step 3",
        "Trade-offs & temporal stability",
        "Accuracy and discovery are separate objectives; no composite policy score is produced.",
    )
    plot = result.summaries.copy()
    plot["novelty_label"] = plot["novelty_bits"].round(2)
    figure = px.scatter(
        plot,
        x="recall_at_k",
        y="coverage",
        color="policy",
        size="novelty_bits",
        hover_data=["concentration_hhi", "top_10_share", "novelty_label"],
        labels={
            "recall_at_k": f"Recall@{result.config.k}",
            "coverage": "Catalog coverage",
            "policy": "Policy",
            "novelty_bits": "Novelty",
        },
        color_discrete_sequence=sig.colorway(NS),
        template=sig.template(NS),
    )
    figure.update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%", margin=dict(t=25))
    sig.chart(NS, figure, key=k("tradeoff_chart"))

    exposure = result.summaries[
        ["policy", "coverage", "novelty_bits", "concentration_hhi", "top_10_share", "fallback_rate"]
    ].copy()
    st.markdown("### Exposure distribution")
    st.dataframe(exposure, width="stretch", hide_index=True)
    st.caption(
        "Novelty is mean self-information from smoothed pre-cutoff item frequency. HHI is the sum of squared recommendation-exposure shares."
    )

    st.markdown("### Fold stability")
    fold_long = result.fold_metrics.melt(
        id_vars=["fold", "policy"], value_vars=["recall_at_k", "ndcg_at_k"], var_name="metric", value_name="value"
    )
    fold_figure = px.line(
        fold_long,
        x="fold",
        y="value",
        color="policy",
        facet_row="metric",
        markers=True,
        labels={"fold": "Temporal fold", "value": "Value", "policy": "Policy"},
        color_discrete_sequence=sig.colorway(NS),
        template=sig.template(NS),
    )
    fold_figure.update_yaxes(tickformat=".0%", matches=None)
    fold_figure.update_layout(height=520, margin=dict(t=30))
    sig.chart(NS, fold_figure, key=k("fold_chart"))


def page_cold_start(result) -> None:
    sig.header("Step 4", "Cold start & subgroup diagnostics")
    sig.note(
        "boundary",
        "**Interpretation:** cold users have no more than the declared number of unique pre-cutoff items — "
        "low-history users, not brand-new users. Cold items have no more than the declared number of pre-cutoff "
        "events. Subgroup gaps are descriptive and context-dependent.",
    )
    cold = result.summaries[
        ["policy", "cold_user_recall_at_k", "cold_item_recall_at_k", "fallback_rate", "users"]
    ].copy()
    st.markdown("### Cold-start evidence")
    st.dataframe(cold, width="stretch", hide_index=True)
    if cold["cold_item_recall_at_k"].isna().all():
        st.info("No evaluable cold-item relevant events occurred under the current thresholds.")

    st.markdown("### Subgroup performance")
    st.dataframe(result.subgroup_metrics, width="stretch", hide_index=True)
    st.markdown("### Max-minus-min subgroup gaps")
    st.dataframe(result.subgroup_gaps, width="stretch", hide_index=True)
    st.warning(
        "Do not infer discrimination or fairness from a gap alone. Review subgroup definition, exposure, eligibility, sample size, measurement, and domain harms."
    )


def page_evidence(data, audit, result, source_label: str) -> None:
    sig.header(
        "Step 5",
        "Evidence pack",
        "Export the data contract, temporal folds, predeclared configuration, policy summaries, paired contrasts, "
        "subgroup tables, user-level metrics, slates, diagnostics, and limitations.",
    )
    metadata = {
        "app": "Recommend Signal",
        "version": __version__,
        "name_status": "Informal clearance screen passed (July 2026); not a trademark opinion.",
        "data_source": source_label,
        "evaluation_type": "Global-timeline expanding-window offline replay",
        "candidate_protocol": "Full eligible catalog; previously interacted items excluded",
        "decision_boundary": "No causal, commercial, satisfaction, retention, or welfare claim",
        "next_step": "Preregister and randomize the final policy in Experiment Signal",
    }
    workbook = build_evidence_workbook(metadata=metadata, audit=audit, result=result)
    st.download_button(
        "Download Recommend Signal evidence pack",
        workbook,
        "recommendsignal-evidence-pack.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key=k("download_evidence_pack"),
    )
    c1, c2 = st.columns(2)
    c1.download_button(
        "Download policy summary CSV",
        dataframe_csv_bytes(result.summaries),
        "recommendsignal-policy-summary.csv",
        "text/csv",
        key=k("download_policy_summary"),
    )
    c2.download_button(
        "Download paired contrasts CSV",
        dataframe_csv_bytes(result.contrasts),
        "recommendsignal-paired-contrasts.csv",
        "text/csv",
        key=k("download_paired_contrasts"),
    )
    st.markdown("### Export metadata")
    st.json(metadata)
    st.info("The workbook deliberately contains no universal recommendation score and no declaration of business lift.")


def page_methods() -> None:
    sig.header("Reference", "Methods & boundaries")
    st.markdown("### What the four policies are")
    st.write(
        "- **Popularity:** ranks unseen eligible items by weighted pre-cutoff interaction frequency.\n"
        "- **Content-based:** cosine similarity between an item-feature vector and the weighted mean of a user's consumed-item features.\n"
        "- **Collaborative:** item-item cosine similarity from the pre-cutoff implicit user-item matrix.\n"
        "- **Hybrid:** a declared weighted combination of within-user full-catalog score ranks. Presets make weights explicit; "
        "they do not prevent repeated tuning, so record one choice before inspecting holdout results."
    )
    st.markdown("### What the metrics mean")
    st.write(
        "- **Recall@K:** observed eligible test items retrieved in the top K divided by observed eligible test items.\n"
        "- **NDCG@K:** binary relevance discounted by log rank and normalized by the ideal ordering.\n"
        "- **Coverage:** distinct recommended items divided by the eligible catalog, averaged across folds.\n"
        "- **Novelty:** mean negative log₂ smoothed pre-cutoff item frequency.\n"
        "- **Concentration:** exposure HHI and top-10-item share."
    )
    st.markdown("### Non-negotiable boundaries")
    st.write(
        "- The evaluator uses a global timeline; later interactions never train an earlier fold.\n"
        "- It evaluates the full eligible catalog and does not use sampled negatives.\n"
        "- Logged noninteraction is not treated as a known dislike.\n"
        "- Item metadata must be historically valid at each cutoff.\n"
        "- Subgroup output is diagnostic, not a fairness verdict.\n"
        "- Offline results do not estimate incremental sales, retention, satisfaction, welfare, or causality. Final policies belong in Experiment Signal."
    )
    st.markdown("### Independent public foundations")
    st.markdown(
        "The implementation is independently written from general public literature on recommender evaluation, including "
        "[Herlocker et al. (2004)](https://doi.org/10.1145/963770.963772), "
        "[Järvelin & Kekäläinen (2002)](https://doi.org/10.1145/582415.582418), "
        "[Steck (2013)](https://doi.org/10.1145/2507157.2507160), "
        "[Ji et al. (2023)](https://doi.org/10.1145/3569930), and "
        "[Tian & Ekstrand (2020)](https://doi.org/10.1145/3343413.3378004)."
    )
    st.caption("No lecture slides, teaching wording, course data, exercises, cases, diagrams, or institution-specific frameworks are included.")


def _show_page(page: str, config: EvaluationConfig) -> None:
    events = st.session_state[k("events")]
    items = st.session_state[k("items")]
    source = st.session_state[k("source_label")]
    if page == "Welcome":
        page_welcome()
    elif page == "1 · Data & temporal contract":
        page_data(events, items, source, config)
    elif page == "Methods & boundaries":
        page_methods()
    else:
        validated, data_audit, evaluation = _evaluate(events, items, config)
        if page == "2 · Offline leaderboard":
            page_leaderboard(evaluation)
        elif page == "3 · Trade-offs & stability":
            page_tradeoffs(evaluation)
        elif page == "4 · Cold start & subgroups":
            page_cold_start(evaluation)
        elif page == "5 · Evidence pack":
            page_evidence(validated, data_audit, evaluation, source)


def _sidebar() -> SidebarChoices:
    """Draw the sidebar lockup, page selector, data source, evaluation contract and status notes."""
    sig.sidebar_brand(NS, SIDEBAR_TAGLINE)
    with st.sidebar:
        st.caption(f"Recommendation policy evidence · v{__version__}")
        page = st.radio("Navigate", PAGES, key=k("page"))
        source = st.radio("Data source", [DEMO_SOURCE, UPLOAD_SOURCE], key=k("data_source"))
        event_upload = item_upload = None
        if source == UPLOAD_SOURCE:
            event_upload = st.file_uploader(
                "Interactions · CSV or XLSX", type=["csv", "xlsx", "xlsm"], key=k("event_upload")
            )
            item_upload = st.file_uploader("Item catalog · CSV or XLSX", type=["csv", "xlsx", "xlsm"], key=k("item_upload"))
        settings = _settings()
        st.divider()
        st.warning("Working title only: Recommend Signal has not received formal trademark clearance.")
        st.caption("Local processing · no telemetry · no causal claims")
    return SidebarChoices(page, source, event_upload, item_upload, settings)


def render() -> None:
    """Draw the whole Recommend Signal app on the current page. Never calls st.set_page_config or st.navigation."""
    sig.apply(NS)
    _ensure_state()
    choices = _sidebar()
    sig.masthead(NS, MASTHEAD_PROMISES, MASTHEAD_KICKER)
    try:
        _load_data(choices)
        _show_page(choices.page, EvaluationConfig(**choices.settings))
    except Exception as exc:
        show_error(exc)
    sig.footer(NS, __version__, FOOTER_LINE)
