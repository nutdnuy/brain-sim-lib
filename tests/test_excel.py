from __future__ import annotations

from openpyxl import Workbook
import pytest

from brain_sim.excel import ExcelInputError, read_excel_expressions


def write_workbook(path, headers, rows) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_read_excel_uses_expression_and_settings(tmp_path) -> None:
    path = tmp_path / "alphas.xlsx"
    write_workbook(
        path,
        ["id", "expression", "universe", "delay", "decay", "neutralization"],
        [["a1", "rank(close)", "TOP1000", 0, 6, "INDUSTRY"]],
    )

    alphas = read_excel_expressions(path)

    assert len(alphas) == 1
    assert alphas[0].row_id == "a1"
    assert alphas[0].expression == "rank(close)"
    assert alphas[0].settings.universe == "TOP1000"
    assert alphas[0].settings.delay == 0
    assert alphas[0].settings.decay == 6
    assert alphas[0].settings.neutralization == "INDUSTRY"


def test_read_excel_generates_row_id_when_missing(tmp_path) -> None:
    path = tmp_path / "alphas.xlsx"
    write_workbook(path, ["expression"], [["close"], ["rank(volume)"]])

    alphas = read_excel_expressions(path)

    assert [alpha.row_id for alpha in alphas] == ["row-2", "row-3"]


def test_read_excel_rejects_missing_expression_header(tmp_path) -> None:
    path = tmp_path / "bad.xlsx"
    write_workbook(path, ["alpha"], [["close"]])

    with pytest.raises(ExcelInputError, match="expression"):
        read_excel_expressions(path)
