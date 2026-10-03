"""Data limits: none locally, demo caps only with SIGNAL_PUBLIC=1, and batched scoring equals one user at a time.

Every test is fast: inputs beyond the demo caps are built by lowering the caps, never by building a huge file.
"""

from __future__ import annotations

from io import BytesIO
import zipfile

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from recommendsignal import limits
from recommendsignal.analysis import evaluate_policies
from recommendsignal.design import EvaluationConfig, make_temporal_folds, validate_inputs
from recommendsignal.errors import DataProblem
from recommendsignal.io import build_evidence_workbook, read_table
from recommendsignal.design import audit_data
from recommendsignal.limits import Limits
from recommendsignal import models


TINY_DEMO = Limits(
    upload_bytes=2_000_000,
    expanded_workbook_bytes=1024,
    table_rows=100,
    table_columns=5,
    catalog_items=50,
    bootstrap_repetitions=100,
)


@pytest.fixture
def tiny_demo_caps(monkeypatch):
    monkeypatch.setattr(limits, "PUBLIC_DEMO", TINY_DEMO)
    return monkeypatch


def _workbook_bomb() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", "x" * 4096)
    return output.getvalue()


def test_local_mode_accepts_input_beyond_the_demo_caps(tiny_demo_caps, demo_events, demo_catalog) -> None:
    tiny_demo_caps.delenv("SIGNAL_PUBLIC", raising=False)
    assert limits.active() == Limits()
    events = read_table("events.csv", demo_events.to_csv(index=False).encode("utf-8"))
    items = read_table("items.csv", demo_catalog.to_csv(index=False).encode("utf-8"))
    assert len(events) > TINY_DEMO.table_rows and len(items.columns) > TINY_DEMO.table_columns
    assert len(items) > TINY_DEMO.catalog_items
    with pytest.raises(DataProblem, match="Could not read"):  # past the size guard; just not a real workbook
        read_table("items.xlsx", _workbook_bomb())
    data = validate_inputs(events, items)
    result = evaluate_policies(data, EvaluationConfig(n_folds=1, bootstrap_repetitions=200))
    assert not result.summaries.empty


def test_public_demo_enforces_its_caps_and_says_so(tiny_demo_caps, demo_events, demo_catalog) -> None:
    tiny_demo_caps.setenv("SIGNAL_PUBLIC", "1")
    cases = [
        (lambda: read_table("big.csv", b"0" * (TINY_DEMO.upload_bytes + 1)), "Uploads are limited"),
        (lambda: read_table("items.xlsx", _workbook_bomb()), "expand to at most"),
        (lambda: read_table("events.csv", demo_events.to_csv(index=False).encode("utf-8")), "100-row limit"),
        (lambda: read_table("wide.csv", b"a,b,c,d,e,f\n1,2,3,4,5,6\n"), "5-column limit"),
        (lambda: validate_inputs(demo_events, demo_catalog), "at most 50 items"),
    ]
    for call, pattern in cases:
        with pytest.raises(DataProblem, match=pattern) as caught:
            call()
        assert limits.DEMO_NOTE in str(caught.value)
    tiny_demo_caps.setattr(limits, "PUBLIC_DEMO", Limits(bootstrap_repetitions=100))
    data = validate_inputs(demo_events, demo_catalog)
    with pytest.raises(DataProblem, match="at most 100 bootstrap repetitions") as caught:
        evaluate_policies(data, EvaluationConfig(bootstrap_repetitions=200))
    assert limits.DEMO_NOTE in str(caught.value)


def test_real_demo_caps_follow_the_previous_release_limits() -> None:
    assert limits.PUBLIC_DEMO.upload_bytes == 50 * 1024 * 1024
    assert limits.PUBLIC_DEMO.table_rows == 500_000
    assert limits.PUBLIC_DEMO.catalog_items == 2_500


def test_running_out_of_memory_is_a_plain_message(monkeypatch) -> None:
    def exhausted(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr("recommendsignal.io.pd.read_csv", exhausted)
    with pytest.raises(DataProblem, match="not enough memory for this file"):
        read_table("huge.csv", b"user_id\nA\n")


def test_batch_size_and_threads_do_not_change_results(monkeypatch, validated) -> None:
    config = EvaluationConfig(k=10, n_folds=2)
    fold = make_temporal_folds(validated.events, config)[0]
    reference = models.evaluate_fold(validated, fold, config)
    monkeypatch.setattr(models, "BATCH_CELLS", 500)  # a handful of users per batch
    monkeypatch.setattr(models, "SCORING_THREADS", 3)
    batched = models.evaluate_fold(validated, fold, config)
    monkeypatch.setattr(models, "IN_PLACE_SIMILARITY_ITEMS", 1)
    in_place = models.evaluate_fold(validated, fold, config)
    pd.testing.assert_frame_equal(batched.user_metrics, reference.user_metrics)
    pd.testing.assert_frame_equal(batched.recommendations, reference.recommendations)
    assert batched.diagnostics == reference.diagnostics
    pd.testing.assert_frame_equal(
        in_place.recommendations.drop(columns="score"), reference.recommendations.drop(columns="score")
    )


def test_linear_top_k_and_shared_popularity_ranks_match_full_sorts() -> None:
    rng = np.random.default_rng(0)
    for _ in range(200):
        users, items, k = rng.integers(1, 20), rng.integers(1, 50), rng.integers(1, 12)
        scores = rng.integers(0, 4, (users, items)).astype(float)  # many ties
        seen = rng.random((users, items)) < rng.random()
        width = min(k, items)
        expected = np.argsort(np.where(seen, np.inf, -scores), axis=1, kind="stable")[:, :width]
        got = models._top_k(scores, seen, width)
        candidates = items - seen.sum(axis=1)
        for row, length in enumerate(np.minimum(candidates, k)):
            assert (got[row, :length] == expected[row, :length]).all()
        shared = np.broadcast_to(scores[0], (users, items))
        np.testing.assert_array_equal(
            models._batch_popularity_rank(np.argsort(scores[0], kind="stable"), seen, candidates),
            models._batch_relative_rank(shared, seen, candidates),
        )


def test_large_tables_get_a_note_sheet_and_keep_their_csv(monkeypatch, validated, result) -> None:
    monkeypatch.setattr("recommendsignal.io.EXCEL_SHEET_CELLS", 1_000)
    payload = build_evidence_workbook(metadata={"app": "Recommend Signal"}, audit=audit_data(validated), result=result)
    slates = pd.read_excel(BytesIO(payload), sheet_name="recommendations")
    assert list(slates.columns) == ["note"] and "contains every row" in slates.iloc[0, 0]
    assert len(pd.read_excel(BytesIO(payload), sheet_name="policy_summary")) == len(result.summaries)


LAZY_APP = """
import recommendsignal.ui.app as recommend_app

recommend_app.LAZY_EXPORT_ROWS = 10
recommend_app.render()
"""


def test_large_evaluations_build_exports_on_click() -> None:
    app = AppTest.from_string(LAZY_APP, default_timeout=180)
    app.run()
    app.sidebar.radio[0].set_value("5 · Evidence pack").run()
    assert not app.exception, [error.value for error in app.exception]
    assert any("prepared when you click it" in str(caption.value) for caption in app.caption)
