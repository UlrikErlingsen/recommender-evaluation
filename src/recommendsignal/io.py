"""Local file input and auditable evidence-pack export."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path

import pandas as pd

from .analysis import EvaluationResult
from .design import DataAudit
from .errors import DataProblem


def read_table(filename: str, payload: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(BytesIO(payload))
        if suffix in {".xlsx", ".xlsm"}:
            workbook = pd.ExcelFile(BytesIO(payload))
            selected = sheet_name if sheet_name in workbook.sheet_names else workbook.sheet_names[0]
            return pd.read_excel(workbook, sheet_name=selected)
    except Exception as exc:  # pragma: no cover - parser messages vary by dependency
        raise DataProblem(f"Could not read {filename}: {exc}") from exc
    raise DataProblem("Upload a CSV or XLSX file.")


def _metadata_rows(metadata: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "field": key,
                "value": json.dumps(value) if isinstance(value, (dict, list, tuple)) else value,
            }
            for key, value in metadata.items()
        ]
    )


def build_evidence_workbook(
    *,
    metadata: dict[str, object],
    audit: DataAudit,
    result: EvaluationResult,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _metadata_rows(metadata).to_excel(writer, sheet_name="read_me", index=False)
        _metadata_rows(asdict(result.config)).to_excel(writer, sheet_name="evaluation_config", index=False)
        audit.overview.to_excel(writer, sheet_name="data_audit", index=False)
        audit.subgroup_counts.to_excel(writer, sheet_name="subgroup_counts", index=False)
        result.folds.to_excel(writer, sheet_name="temporal_folds", index=False)
        result.summaries.to_excel(writer, sheet_name="policy_summary", index=False)
        result.contrasts.to_excel(writer, sheet_name="paired_contrasts", index=False)
        result.fold_metrics.to_excel(writer, sheet_name="fold_metrics", index=False)
        result.subgroup_metrics.to_excel(writer, sheet_name="subgroups", index=False)
        result.subgroup_gaps.to_excel(writer, sheet_name="subgroup_gaps", index=False)
        result.diagnostics.to_excel(writer, sheet_name="fold_diagnostics", index=False)
        pd.DataFrame({"warning": result.warnings}).to_excel(writer, sheet_name="limitations", index=False)
        result.user_metrics.to_excel(writer, sheet_name="user_metrics", index=False)
        result.recommendations.to_excel(writer, sheet_name="recommendations", index=False)
    return output.getvalue()


def dataframe_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")
