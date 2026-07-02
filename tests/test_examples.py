from __future__ import annotations

import csv
import json
import sys
import types
from pathlib import Path
from urllib.parse import unquote

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
NOTEBOOK = EXAMPLES / "Tutorial 1 - Excel Batch Alpha Simulation.ipynb"
WORKBOOK = EXAMPLES / "data" / "tutorial_01_alphas.xlsx"
EXPECTED_SUMMARY = EXAMPLES / "expected" / "tutorial_01_summary.csv"
EXAMPLES_README = EXAMPLES / "README.md"


def _load_notebook() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def _code_cell_source(notebook: dict) -> str:
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )


def test_examples_index_links_tutorial_and_sample_assets() -> None:
    text = EXAMPLES_README.read_text(encoding="utf-8")

    assert "Tutorial 1 - Excel Batch Alpha Simulation.ipynb" in text
    assert "data/tutorial_01_alphas.xlsx" in text
    assert "expected/tutorial_01_summary.csv" in text
    assert "offline" in text.lower()


def test_root_readme_points_to_examples() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    encoded_target = "examples/Tutorial%201%20-%20Excel%20Batch%20Alpha%20Simulation.ipynb"

    assert "## Examples" in text
    assert "examples/Tutorial 1 - Excel Batch Alpha Simulation.ipynb" in text
    assert f"]({encoded_target})" in text
    assert (ROOT / unquote(encoded_target)).exists()
    assert "offline tutorial" in text.lower()


def test_tutorial_notebook_has_required_sections_and_dry_run_flag() -> None:
    notebook = _load_notebook()
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )
    code_source = _code_cell_source(notebook)

    required_sections = [
        "# Tutorial 1 - Excel Batch Alpha Simulation",
        "## 1. What This Tutorial Builds",
        "## 2. Create A Sample Excel Queue",
        "## 3. Understand Batch Simulation Artifacts",
        "## 4. Run The Offline Simulation",
        "## 5. Inspect Summary And Retry Queue",
        "## 6. Live BRAIN Run After Login",
        "## 7. Batch Timeout And Retry Rules",
    ]
    for heading in required_sections:
        assert heading in source

    assert "DRY_RUN = True" in code_source
    assert "BatchRunner" in code_source
    assert "FakeTutorialBrainClient" in code_source


def test_tutorial_code_cells_do_not_run_live_brain_commands() -> None:
    notebook = _load_notebook()
    code_source = _code_cell_source(notebook)

    blocked_fragments = [
        "brain-sim login",
        "brain-sim simulate-excel",
        "BrainAuth(",
        "BrainClient(",
        "brain_sim.auth",
        "brain_sim.client",
        "subprocess",
        "os.system",
        "requests.Session()",
        "requests.",
        "simulate-excel",
        "login --print-link",
        "login --notify-email",
        "api.worldquantbrain.com",
        ".brain_credentials",
    ]
    for fragment in blocked_fragments:
        assert fragment not in code_source


def test_sample_workbook_has_expected_alpha_rows() -> None:
    workbook = load_workbook(WORKBOOK, data_only=True)
    sheet = workbook["alphas"]
    rows = list(sheet.iter_rows(values_only=True))

    assert rows[0] == (
        "id",
        "expression",
        "region",
        "universe",
        "delay",
        "decay",
        "neutralization",
        "truncation",
        "nanHandling",
        "language",
        "visualization",
    )
    assert len(rows) == 5
    assert rows[1][0] == "tutorial-001"
    assert rows[1][1] == "rank(ts_mean(volume, 10))"
    assert {row[3] for row in rows[1:]} == {"TOP3000"}
    assert {row[5] for row in rows[1:]} == {5}


def test_expected_summary_matches_offline_batch_results() -> None:
    with EXPECTED_SUMMARY.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert [row["row_id"] for row in rows] == [
        "tutorial-001",
        "tutorial-002",
        "tutorial-003",
        "tutorial-004",
    ]
    assert [row["status"] for row in rows] == ["complete", "complete", "complete", "complete"]
    assert [row["alpha_id"] for row in rows] == [
        "tutorial-alpha-1",
        "tutorial-alpha-2",
        "tutorial-alpha-3",
        "tutorial-alpha-4",
    ]
    assert all(row["simulation_location"].startswith("/simulations/tutorial-") for row in rows)


def test_tutorial_code_cells_execute_offline(tmp_path, monkeypatch) -> None:
    notebook = _load_notebook()
    module = types.ModuleType("__tutorial_test__")
    namespace: dict[str, object] = module.__dict__
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.chdir(ROOT)

    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        compiled = compile(source, f"{NOTEBOOK.name}:cell-{index}", "exec")
        exec(compiled, namespace)

    summary_path = ROOT / "examples" / "runs" / "tutorial_01_offline" / "summary.csv"
    assert summary_path.exists()
    with summary_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert [row["status"] for row in rows] == ["complete", "complete", "complete", "complete"]
