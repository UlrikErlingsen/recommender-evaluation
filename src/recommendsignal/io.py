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
from .errors import DataProblem, out_of_memory_message
from .limits import active, demo_limit

# Size, row and column caps exist only in a public demo (SIGNAL_PUBLIC=1); see limits.py.
CSV_CHUNK_ROWS = 500_000
# Excel holds at most 1,048,576 rows per sheet, and writing millions of cells into a workbook takes minutes and
# gigabytes. A sheet above either bound carries a note; the full table is offered as a CSV download.
EXCEL_SHEET_ROWS = 1_048_575
EXCEL_SHEET_CELLS = 2_000_000
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


def _check_shape(rows: int, columns: int) -> None:
    limits = active()
    if limits.table_rows is not None and rows > limits.table_rows:
        raise DataProblem(demo_limit(f"The table exceeds the demo's {limits.table_rows:,}-row limit."))
    if limits.table_columns is not None and columns > limits.table_columns:
        raise DataProblem(demo_limit(f"The table exceeds the demo's {limits.table_columns}-column limit."))


def read_table(filename: str, payload: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    limits = active()
    if not payload:
        raise DataProblem("This file is empty.")
    if limits.upload_bytes is not None and len(payload) > limits.upload_bytes:
        raise DataProblem(demo_limit(f"Uploads are limited to {limits.upload_bytes // (1024 * 1024)} MB in this demo."))
    try:
        if suffix == ".csv":
            chunks: list[pd.DataFrame] = []
            rows = 0
            for chunk in pd.read_csv(BytesIO(payload), chunksize=CSV_CHUNK_ROWS):
                rows += len(chunk)
                _check_shape(rows, len(chunk.columns))
                chunks.append(chunk)
            frame = chunks[0] if len(chunks) == 1 else pd.concat(chunks, ignore_index=True)
            del chunks
        elif suffix in {".xlsx", ".xlsm"}:
            if limits.expanded_workbook_bytes is not None:
                with zipfile.ZipFile(BytesIO(payload)) as workbook_zip:
                    expanded = sum(member.file_size for member in workbook_zip.infolist())
                if expanded > limits.expanded_workbook_bytes:
                    raise DataProblem(
                        demo_limit(f"Workbooks may expand to at most {limits.expanded_workbook_bytes // (1024 * 1024)} MB.")
                    )
            workbook = pd.ExcelFile(BytesIO(payload))
            selected = sheet_name if sheet_name in workbook.sheet_names else workbook.sheet_names[0]
            frame = pd.read_excel(workbook, sheet_name=selected)
        else:
            raise DataProblem("Upload a CSV or XLSX file.")
    except DataProblem:
        raise
    except MemoryError as exc:
        raise DataProblem(out_of_memory_message("this file")) from exc
    except Exception as exc:  # pragma: no cover - parser messages vary by dependency
        raise DataProblem(f"Could not read {filename}: {exc}") from exc
    _check_shape(len(frame), len(frame.columns))
    return frame


def _sheet(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame itself, or a note pointing to its CSV when it is too large for a workbook sheet."""
    if len(frame) > EXCEL_SHEET_ROWS or frame.size > EXCEL_SHEET_CELLS:
        return pd.DataFrame(
            {
                "note": [
                    f"This table has {len(frame):,} rows × {len(frame.columns)} columns, too large for a workbook "
                    "sheet. Download its CSV from the Evidence pack page: it contains every row."
                ]
            }
        )
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
        _sheet(result.user_metrics).to_excel(writer, sheet_name="user_metrics", index=False)
        _sheet(result.recommendations).to_excel(writer, sheet_name="recommendations", index=False)
    return output.getvalue()


def dataframe_csv_bytes(frame: pd.DataFrame) -> bytes:
    return safe_frame(frame).to_csv(index=False).encode("utf-8")
