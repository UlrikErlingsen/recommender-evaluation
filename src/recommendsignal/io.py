"""Local file input and auditable evidence-pack export."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import re
import zipfile

import pandas as pd

from .analysis import EvaluationResult
from .design import DataAudit
from .errors import DataProblem

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_WORKBOOK_BYTES = 200 * 1024 * 1024
MAX_TABLE_ROWS = 500_000
MAX_TABLE_COLUMNS = 200
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _safe_cell(value: object) -> object:
    if isinstance(value, str):
        cleaned = _ILLEGAL_XML.sub("", value)
        if cleaned.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + cleaned
        return cleaned
    return value


def safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Neutralize spreadsheet formulas in object cells and column headers."""
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].map(_safe_cell)
    result.columns = [_safe_cell(str(column)) for column in result.columns]
    return result


def read_table(filename: str, payload: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if not payload:
        raise DataProblem("This file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DataProblem("Uploads are limited to 50 MB. Reduce the log to the needed columns and period.")
    try:
        if suffix == ".csv":
            frame = pd.read_csv(BytesIO(payload))
        elif suffix in {".xlsx", ".xlsm"}:
            with zipfile.ZipFile(BytesIO(payload)) as workbook_zip:
                expanded = sum(member.file_size for member in workbook_zip.infolist())
            if expanded > MAX_EXPANDED_WORKBOOK_BYTES:
                raise DataProblem("This workbook expands beyond 200 MB. Remove unrelated sheets before upload.")
            workbook = pd.ExcelFile(BytesIO(payload))
            selected = sheet_name if sheet_name in workbook.sheet_names else workbook.sheet_names[0]
            frame = pd.read_excel(workbook, sheet_name=selected)
        else:
            raise DataProblem("Upload a CSV or XLSX file.")
    except DataProblem:
        raise
    except Exception as exc:  # pragma: no cover - parser messages vary by dependency
        raise DataProblem(f"Could not read {filename}: {exc}") from exc
    if len(frame) > MAX_TABLE_ROWS:
        raise DataProblem(f"The table exceeds the {MAX_TABLE_ROWS:,}-row safety limit; sample or shorten the log.")
    if len(frame.columns) > MAX_TABLE_COLUMNS:
        raise DataProblem(f"The table exceeds the {MAX_TABLE_COLUMNS}-column safety limit; keep the needed columns.")
    return frame


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
        safe_frame(_metadata_rows(metadata)).to_excel(writer, sheet_name="read_me", index=False)
        safe_frame(_metadata_rows(asdict(result.config))).to_excel(writer, sheet_name="evaluation_config", index=False)
        audit.overview.to_excel(writer, sheet_name="data_audit", index=False)
        audit.subgroup_counts.to_excel(writer, sheet_name="subgroup_counts", index=False)
        result.folds.to_excel(writer, sheet_name="temporal_folds", index=False)
        result.summaries.to_excel(writer, sheet_name="policy_summary", index=False)
        result.contrasts.to_excel(writer, sheet_name="paired_contrasts", index=False)
        result.fold_metrics.to_excel(writer, sheet_name="fold_metrics", index=False)
        result.subgroup_metrics.to_excel(writer, sheet_name="subgroups", index=False)
        result.subgroup_gaps.to_excel(writer, sheet_name="subgroup_gaps", index=False)
        result.diagnostics.to_excel(writer, sheet_name="fold_diagnostics", index=False)
        safe_frame(pd.DataFrame({"warning": result.warnings})).to_excel(writer, sheet_name="limitations", index=False)
        result.user_metrics.to_excel(writer, sheet_name="user_metrics", index=False)
        result.recommendations.to_excel(writer, sheet_name="recommendations", index=False)
    return output.getvalue()


def dataframe_csv_bytes(frame: pd.DataFrame) -> bytes:
    return safe_frame(frame).to_csv(index=False).encode("utf-8")
