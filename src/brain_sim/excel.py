from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .models import AlphaExpression, SimulationSettings


class ExcelInputError(ValueError):
    pass


SETTING_COLUMNS = set(SimulationSettings.__dataclass_fields__.keys())


def _coerce_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() == "true":
            return True
        if stripped.lower() == "false":
            return False
        return stripped
    return value


def read_excel_expressions(path: str | Path, *, sheet_name: str | None = None) -> list[AlphaExpression]:
    workbook = load_workbook(Path(path), data_only=True)
    sheet = workbook[sheet_name] if sheet_name else workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ExcelInputError("Excel file is empty.")

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    header_to_index = {header: index for index, header in enumerate(headers) if header}
    if "expression" not in header_to_index:
        raise ExcelInputError("Excel input must contain an expression column.")

    output: list[AlphaExpression] = []
    for excel_row_number, row in enumerate(rows[1:], start=2):
        expression = _coerce_value(row[header_to_index["expression"]])
        if not expression:
            continue
        row_id = ""
        if "id" in header_to_index:
            row_id = str(_coerce_value(row[header_to_index["id"]]))
        if not row_id:
            row_id = f"row-{excel_row_number}"

        overrides: dict[str, Any] = {}
        metadata: dict[str, Any] = {"excel_row": excel_row_number}
        for header, index in header_to_index.items():
            value = _coerce_value(row[index] if index < len(row) else "")
            if header in SETTING_COLUMNS:
                overrides[header] = value
            elif header not in {"id", "expression"}:
                metadata[header] = value

        output.append(
            AlphaExpression(
                row_id=row_id,
                expression=str(expression),
                settings=SimulationSettings.from_overrides(overrides),
                metadata=metadata,
            )
        )
    return output
