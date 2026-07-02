from __future__ import annotations

import csv
import json
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DATA_DIR = EXAMPLES / "data"
EXPECTED_DIR = EXAMPLES / "expected"
NOTEBOOK_PATH = EXAMPLES / "Tutorial 1 - Excel Batch Alpha Simulation.ipynb"
WORKBOOK_PATH = DATA_DIR / "tutorial_01_alphas.xlsx"
SUMMARY_PATH = EXPECTED_DIR / "tutorial_01_summary.csv"
FIXED_WORKBOOK_DATETIME = datetime(2026, 1, 1, 0, 0, 0)
FIXED_WORKBOOK_TIMESTAMP = "2026-01-01T00:00:00Z"
FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)
CORE_XML_NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

for prefix, uri in CORE_XML_NAMESPACES.items():
    ET.register_namespace(prefix, uri)

ALPHA_ROWS = [
    ("tutorial-001", "rank(ts_mean(volume, 10))"),
    ("tutorial-002", "rank(ts_mean(volume, 20))"),
    ("tutorial-003", "rank(ts_mean(returns, 5))"),
    ("tutorial-004", "rank(ts_std_dev(returns, 20))"),
]

SUMMARY_FIELDS = [
    "row_id",
    "alpha_hash",
    "status",
    "alpha_id",
    "simulation_location",
    "sharpe",
    "fitness",
    "returns",
    "turnover",
    "drawdown",
    "margin",
    "longCount",
    "shortCount",
    "failed_checks",
    "warning_checks",
    "pending_checks",
    "error",
]


def _normalize_core_properties(data: bytes) -> bytes:
    root = ET.fromstring(data)
    dcterms = CORE_XML_NAMESPACES["dcterms"]
    for tag_name in ("created", "modified"):
        element = root.find(f"{{{dcterms}}}{tag_name}")
        if element is not None:
            element.text = FIXED_WORKBOOK_TIMESTAMP
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def _canonicalize_xml(data: bytes) -> bytes:
    return ET.canonicalize(data.decode("utf-8")).encode("utf-8")


def _normalize_xlsx_zip(path: Path) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(path, "r") as source:
            with zipfile.ZipFile(
                temp_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as target:
                for source_info in sorted(source.infolist(), key=lambda info: info.filename):
                    data = source.read(source_info.filename)
                    if source_info.filename == "docProps/core.xml":
                        data = _normalize_core_properties(data)
                    if source_info.filename.endswith((".xml", ".rels")):
                        data = _canonicalize_xml(data)
                    target_info = zipfile.ZipInfo(source_info.filename, FIXED_ZIP_DATETIME)
                    target_info.compress_type = zipfile.ZIP_DEFLATED
                    target_info.create_system = 0
                    target_info.external_attr = 0o600 << 16
                    target.writestr(target_info, data)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def build_workbook() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.properties.created = FIXED_WORKBOOK_DATETIME
    workbook.properties.modified = FIXED_WORKBOOK_DATETIME
    sheet = workbook.active
    sheet.title = "alphas"
    sheet.append(
        [
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
        ]
    )
    for row_id, expression in ALPHA_ROWS:
        sheet.append(
            [
                row_id,
                expression,
                "USA",
                "TOP3000",
                1,
                5,
                "SUBINDUSTRY",
                0.08,
                "OFF",
                "FASTEXPR",
                False,
            ]
        )
    workbook.save(WORKBOOK_PATH)
    _normalize_xlsx_zip(WORKBOOK_PATH)


def build_expected_summary() -> None:
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for index, (row_id, _expression) in enumerate(ALPHA_ROWS, start=1):
            writer.writerow(
                {
                    "row_id": row_id,
                    "alpha_hash": f"tutorial-hash-{index}",
                    "status": "complete",
                    "alpha_id": f"tutorial-alpha-{index}",
                    "simulation_location": f"/simulations/tutorial-{index}",
                    "sharpe": f"{1.0 + index / 10:.2f}",
                    "fitness": f"{0.5 + index / 10:.2f}",
                    "returns": f"{0.03 + index / 100:.2f}",
                    "turnover": f"{0.10 + index / 100:.2f}",
                    "drawdown": f"{0.02 + index / 100:.2f}",
                    "margin": "",
                    "longCount": "",
                    "shortCount": "",
                    "failed_checks": "",
                    "warning_checks": "",
                    "pending_checks": "",
                    "error": "",
                }
            )


def markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source.splitlines()],
    }


def code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source.splitlines()],
    }


def build_notebook() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    cells = [
        markdown_cell(
            """# Tutorial 1 - Excel Batch Alpha Simulation

This notebook walks through an offline batch simulation workflow for alpha expressions stored in Excel. It uses a deterministic local fake client so the example can be run without BRAIN credentials."""
        ),
        markdown_cell(
            """## 1. What This Tutorial Builds

You will load a small Excel queue, turn each row into a simulation payload, run the batch runner locally, and compare the generated artifacts with an expected summary file."""
        ),
        code_cell(
            """from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brain_sim.batch import BatchRunner
from brain_sim.excel import read_excel_expressions
from brain_sim.payloads import build_payload_record


DRY_RUN = True
CWD = Path.cwd().resolve()
ROOT = CWD if (CWD / "examples").exists() else CWD.parent if CWD.name == "examples" else CWD
EXAMPLE_DIR = ROOT / "examples"
EXCEL_PATH = EXAMPLE_DIR / "data" / "tutorial_01_alphas.xlsx"
RUN_DIR = EXAMPLE_DIR / "runs" / "tutorial_01_offline"
EXPECTED_SUMMARY_PATH = EXAMPLE_DIR / "expected" / "tutorial_01_summary.csv"

print(f"Using Excel queue: {EXCEL_PATH}")
print(f"Writing offline artifacts to: {RUN_DIR}")"""
        ),
        markdown_cell(
            """## 2. Create A Sample Excel Queue

The tutorial workbook has one `alphas` sheet. Each row contains an identifier, a Fast Expression, and the settings needed to build a regular simulation payload."""
        ),
        code_cell(
            """alpha_rows = read_excel_expressions(EXCEL_PATH, sheet_name="alphas")

for alpha in alpha_rows:
    print(alpha.row_id, alpha.expression, alpha.settings.universe, alpha.settings.decay)"""
        ),
        markdown_cell(
            """## 3. Understand Batch Simulation Artifacts

`build_payload_record` converts each Excel row into a payload plus a hash used for deduplication. The tutorial pins readable hashes so the generated offline summary matches the checked-in expected CSV exactly."""
        ),
        code_cell(
            """payload_records = []

for index, alpha in enumerate(alpha_rows, start=1):
    record = build_payload_record(alpha)
    tutorial_record = record.__class__(
        row_id=record.row_id,
        alpha_hash=f"tutorial-hash-{index}",
        payload=record.payload,
        metadata=record.metadata,
    )
    payload_records.append(tutorial_record)

for record in payload_records:
    print(record.row_id, record.alpha_hash, record.payload["regular"])"""
        ),
        markdown_cell(
            """## 4. Run The Offline Simulation

The fake client below implements the same methods the batch runner needs. It returns deterministic simulation locations, alpha IDs, and metrics for a fully local dry run."""
        ),
        code_cell(
            """@dataclass(frozen=True)
class TutorialRateLimitState:
    limit: int | None
    remaining: int | None
    reset_seconds: int | None


@dataclass(frozen=True)
class TutorialSubmitResult:
    status_code: int
    location: str
    body: Any
    headers: dict[str, str]
    rate_limit: TutorialRateLimitState


@dataclass(frozen=True)
class TutorialPollResult:
    status: str
    body: Any
    events: list[dict[str, Any]]


class FakeTutorialBrainClient:
    def __init__(self) -> None:
        self._next_simulation = 0
        self._poll_bodies: dict[str, dict[str, Any]] = {}

    def submit(self, payload: dict[str, Any] | list[dict[str, Any]]) -> TutorialSubmitResult:
        self._next_simulation += 1
        location = f"/simulations/tutorial-{self._next_simulation}"
        alpha_id = f"tutorial-alpha-{self._next_simulation}"
        self._poll_bodies[location] = {"alpha": alpha_id, "status": "COMPLETE"}
        return TutorialSubmitResult(
            status_code=201,
            location=location,
            body={"id": f"tutorial-{self._next_simulation}"},
            headers={"Location": location},
            rate_limit=TutorialRateLimitState(limit=None, remaining=None, reset_seconds=None),
        )

    def poll(self, location: str, *, timeout_seconds: float) -> TutorialPollResult:
        body = self._poll_bodies[location]
        return TutorialPollResult(status="complete", body=body, events=[{"body": body}])

    def fetch_alpha(self, alpha_id: str) -> dict[str, Any]:
        index = int(alpha_id.rsplit("-", 1)[-1])
        return {
            "id": alpha_id,
            "status": "UNSUBMITTED",
            "is": {
                "sharpe": f"{1.0 + index / 10:.2f}",
                "fitness": f"{0.5 + index / 10:.2f}",
                "returns": f"{0.03 + index / 100:.2f}",
                "turnover": f"{0.10 + index / 100:.2f}",
                "drawdown": f"{0.02 + index / 100:.2f}",
                "checks": [],
            },
        }

    def fetch_recordset(self, alpha_id: str, recordset_name: str) -> dict[str, Any]:
        return {"alpha_id": alpha_id, "recordset": recordset_name, "rows": []}


if not DRY_RUN:
    raise RuntimeError("This tutorial run cell only executes in DRY_RUN mode.")

shutil.rmtree(RUN_DIR, ignore_errors=True)
tutorial_client_class = FakeTutorialBrainClient
runner = BatchRunner(tutorial_client_class(), RUN_DIR)
run_result = runner.run(payload_records, batch_size=1, poll_timeout_seconds=5)
run_result"""
        ),
        markdown_cell(
            """## 5. Inspect Summary And Retry Queue

The offline run writes the same artifact shape as a live run: `summary.csv`, raw submit and poll logs, alpha detail JSON files, a local cache, and an empty retry queue when every row completes."""
        ),
        code_cell(
            """summary_path = RUN_DIR / "summary.csv"
retry_queue_path = RUN_DIR / "retry_queue.jsonl"

with summary_path.open(newline="", encoding="utf-8") as f:
    actual_summary = list(csv.DictReader(f))
with EXPECTED_SUMMARY_PATH.open(newline="", encoding="utf-8") as f:
    expected_summary = list(csv.DictReader(f))

print(f"Summary rows: {len(actual_summary)}")
print(f"Retry queue exists: {retry_queue_path.exists()}")
print(f"Matches expected summary: {actual_summary == expected_summary}")
actual_summary"""
        ),
        markdown_cell(
            """## 6. Live BRAIN Run After Login

After you have valid BRAIN credentials, run the live commands from a terminal instead of a notebook code cell:

```bash
brain-sim login --print-link --credentials-file ~/.brain_credentials
brain-sim simulate-excel examples/data/tutorial_01_alphas.xlsx --sheet alphas --batch-size 4 --poll-timeout-seconds 1800
```"""
        ),
        markdown_cell(
            """## 7. Batch Timeout And Retry Rules

Use a longer poll timeout for live jobs because the API may accept a simulation before the alpha result is ready. If a row fails or times out, inspect `retry_queue.jsonl`, adjust the expression or timeout, and rerun only the rows that still need attention."""
        ),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    build_workbook()
    build_expected_summary()
    build_notebook()


if __name__ == "__main__":
    main()
