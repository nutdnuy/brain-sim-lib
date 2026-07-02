from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from brain_sim.results import RunStore, summarize_alpha


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_store_creates_directory_structure(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    assert store.run_dir.is_dir()
    assert (store.run_dir / "raw").is_dir()
    assert (store.run_dir / "alphas").is_dir()
    assert (store.run_dir / "recordsets").is_dir()


def test_append_jsonl_adds_timestamp_and_serializes_values(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    store.append_jsonl(
        "submit_results.jsonl",
        {"path": Path("alpha.txt"), "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
        row_id="r1",
        status="complete",
    )
    store.append_jsonl("submit_results.jsonl", {"row_id": "r2", "status": "failed"})

    rows = read_jsonl(tmp_path / "run-1" / "submit_results.jsonl")
    assert len(rows) == 2
    assert rows[0]["row_id"] == "r1"
    assert rows[0]["status"] == "complete"
    assert rows[0]["path"] == "alpha.txt"
    assert rows[0]["created_at"] == "2026-01-01T00:00:00+00:00"
    assert "timestamp" in rows[0]
    assert rows[1]["row_id"] == "r2"


def test_append_jsonl_context_overrides_body_row_and_status(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    store.append_jsonl(
        "submit_results.jsonl",
        {"row_id": "body-row", "status": "COMPLETE", "tags": {"b", "a"}},
        row_id="run-row",
        status="poll_error",
    )

    rows = read_jsonl(tmp_path / "run-1" / "submit_results.jsonl")
    assert rows[0]["row_id"] == "run-row"
    assert rows[0]["status"] == "poll_error"
    assert rows[0]["tags"] == ["a", "b"]


def test_append_jsonl_serializes_mixed_type_sets_deterministically(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    store.append_jsonl("events.jsonl", {"tags": {1, "1"}})

    rows = read_jsonl(tmp_path / "run-1" / "events.jsonl")
    assert rows[0]["tags"] == ["1", 1]


def test_write_json_and_append_jsonl_reject_paths_outside_run_dir(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    for method_name in ("write_json", "append_jsonl"):
        method = getattr(store, method_name)
        try:
            method("../escape.json", {"bad": True})
        except ValueError as exc:
            assert "artifact path" in str(exc)
        else:
            raise AssertionError(f"{method_name} accepted path traversal")


def test_append_raw_event_sanitizes_event_name(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    path = store.append_raw_event("../submit/results", {"ok": True}, row_id="r1", status="complete")

    assert path.parent == tmp_path / "run-1" / "raw"
    assert path.name.endswith(".jsonl")
    assert "/" not in path.name


def test_write_manifest_and_summary_appends_with_stable_headers(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")
    store.write_manifest({"run_id": "run-1"})
    store.write_summary(
        [
            {
                "row_id": "r1",
                "alpha_hash": "h1",
                "status": "complete",
                "alpha_id": "alpha-1",
                "sharpe": 1.2,
                "fitness": 0.8,
                "failed_checks": "",
                "pending_checks": "",
                "error": "",
            }
        ]
    )
    store.write_summary(
        [
            {
                "row_id": "r2",
                "alpha_hash": "h2",
                "status": "submit_error",
                "alpha_id": "",
                "error": "bad expression",
                "ignored": "not written",
            }
        ]
    )

    manifest = json.loads((tmp_path / "run-1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-1"
    with (tmp_path / "run-1" / "summary.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        headers = f.seek(0) or f.readline().strip().split(",")
    assert headers == [
        "row_id",
        "alpha_hash",
        "status",
        "alpha_id",
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
    assert [row["row_id"] for row in rows] == ["r1", "r2"]
    assert rows[0]["alpha_id"] == "alpha-1"
    assert rows[1]["error"] == "bad expression"
    assert "ignored" not in rows[1]


def test_write_summary_rejects_existing_header_mismatch(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")
    (tmp_path / "run-1" / "summary.csv").write_text("old,header\n1,2\n", encoding="utf-8")

    try:
        store.write_summary([{"row_id": "r1"}])
    except ValueError as exc:
        assert "summary.csv header" in str(exc)
    else:
        raise AssertionError("write_summary accepted a mismatched header")


def test_alpha_detail_saves_under_alpha_specific_file(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    path = store.write_alpha_detail("alpha/1", {"id": "alpha/1", "is": {"sharpe": 1.2}})

    assert path.parent == tmp_path / "run-1" / "alphas"
    assert path.name.startswith("alpha_1-")
    assert json.loads(path.read_text(encoding="utf-8"))["id"] == "alpha/1"


def test_safe_filenames_include_hash_to_avoid_collisions(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    path_a = store.write_alpha_detail("alpha/1", {"id": "alpha/1"})
    path_b = store.write_alpha_detail("alpha:1", {"id": "alpha:1"})

    assert path_a.name != path_b.name
    assert json.loads(path_a.read_text(encoding="utf-8"))["id"] == "alpha/1"
    assert json.loads(path_b.read_text(encoding="utf-8"))["id"] == "alpha:1"


def test_recordset_saving_preserves_json_and_wraps_raw_text(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    json_path = store.write_recordset("alpha-1", "pnl", [{"date": "2026-01-01", "pnl": 0.1}])
    raw_path = store.write_recordset("alpha-1", "logs", "not json")

    assert json.loads(json_path.read_text(encoding="utf-8")) == [{"date": "2026-01-01", "pnl": 0.1}]
    assert json.loads(raw_path.read_text(encoding="utf-8")) == {"raw_text": "not json"}


def test_recordset_saving_preserves_existing_raw_text_wrapper(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    path = store.write_recordset("alpha-1", "logs", {"raw_text": "not json"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"raw_text": "not json"}


def test_retry_queue_is_rewritten_for_failed_entries(tmp_path) -> None:
    store = RunStore(tmp_path / "run-1")

    store.write_retry_queue([{"row_id": "r1", "status": "submit_error", "error": "bad"}])
    store.write_retry_queue([{"row_id": "r2", "status": "poll_error", "error": "timeout"}])

    rows = read_jsonl(tmp_path / "run-1" / "retry_queue.jsonl")
    assert len(rows) == 1
    assert rows[0]["row_id"] == "r2"
    assert rows[0]["status"] == "poll_error"
    assert "timestamp" in rows[0]
    assert not (tmp_path / "run-1" / "retry_queue.jsonl.tmp").exists()


def test_summarize_alpha_extracts_metrics_and_checks() -> None:
    detail = {
        "id": "alpha-1",
        "status": "UNSUBMITTED",
        "is": {
            "sharpe": 1.2,
            "fitness": 0.8,
            "returns": 0.05,
            "turnover": 0.2,
            "drawdown": 0.1,
            "margin": 0.02,
            "longCount": 123,
            "shortCount": 98,
            "checks": [
                {"name": "LOW_SHARPE", "result": "FAIL"},
                {"name": "SELF_CORRELATION", "result": "PENDING"},
                {"name": "CONCENTRATION", "result": "WARNING"},
                {"name": "LOW_TURNOVER", "result": "PASS"},
            ],
        },
    }

    row = summarize_alpha(detail)

    assert row["alpha_id"] == "alpha-1"
    assert row["status"] == "UNSUBMITTED"
    assert row["sharpe"] == 1.2
    assert row["fitness"] == 0.8
    assert row["returns"] == 0.05
    assert row["turnover"] == 0.2
    assert row["drawdown"] == 0.1
    assert row["margin"] == 0.02
    assert row["longCount"] == 123
    assert row["shortCount"] == 98
    assert row["failed_checks"] == "LOW_SHARPE"
    assert row["warning_checks"] == "CONCENTRATION"
    assert row["pending_checks"] == "SELF_CORRELATION"


def test_summarize_alpha_tolerates_missing_or_malformed_fields() -> None:
    empty = summarize_alpha(None)
    malformed = summarize_alpha({"id": "alpha-2", "is": {"checks": ["bad", {"result": "FAIL"}]}})

    assert empty["alpha_id"] == ""
    assert empty["status"] == ""
    assert empty["failed_checks"] == ""
    assert malformed["alpha_id"] == "alpha-2"
    assert malformed["sharpe"] == ""
    assert malformed["failed_checks"] == ""


def test_summarize_alpha_accepts_poll_completion_shape() -> None:
    row = summarize_alpha({"alpha": "alpha-1", "status": "COMPLETE"})

    assert row["alpha_id"] == "alpha-1"
    assert row["status"] == "COMPLETE"
