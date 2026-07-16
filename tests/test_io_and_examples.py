from __future__ import annotations

from io import BytesIO

import pandas as pd

from recommendsignal.design import audit_data
from recommendsignal.examples import make_demo_catalog, make_demo_events
from recommendsignal.io import build_evidence_workbook, read_table


def test_examples_are_deterministic() -> None:
    pd.testing.assert_frame_equal(make_demo_events(), make_demo_events())
    pd.testing.assert_frame_equal(make_demo_catalog(), make_demo_catalog())


def test_committed_examples_match_generator(demo_events, demo_catalog) -> None:
    committed_events = pd.read_csv("examples/recommendsignal-fictional-events.csv")
    committed_catalog = pd.read_csv("examples/recommendsignal-fictional-items.csv")
    pd.testing.assert_frame_equal(committed_events, demo_events, check_dtype=False)
    pd.testing.assert_frame_equal(committed_catalog, demo_catalog, check_dtype=False)


def test_read_table_uses_named_workbook_sheet() -> None:
    payload = BytesIO()
    with pd.ExcelWriter(payload, engine="openpyxl") as writer:
        pd.DataFrame({"wrong": [1]}).to_excel(writer, sheet_name="first", index=False)
        pd.DataFrame({"user_id": ["U1"]}).to_excel(writer, sheet_name="interactions", index=False)
    frame = read_table("test.xlsx", payload.getvalue(), sheet_name="interactions")
    assert list(frame.columns) == ["user_id"]


def test_evidence_workbook_contains_auditable_sheets(validated, result) -> None:
    payload = build_evidence_workbook(
        metadata={"app": "RecommendSignal", "boundary": "offline only"},
        audit=audit_data(validated),
        result=result,
    )
    workbook = pd.ExcelFile(BytesIO(payload))
    assert {
        "read_me",
        "evaluation_config",
        "temporal_folds",
        "policy_summary",
        "paired_contrasts",
        "subgroups",
        "user_metrics",
        "recommendations",
        "limitations",
    }.issubset(workbook.sheet_names)
