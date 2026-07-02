from __future__ import annotations

import csv
import json
from pathlib import Path

from brain_sim.batch import BatchRunner, chunk_records, extract_alpha_ids
from brain_sim.client import PollResult, SubmitResult
from brain_sim.models import PayloadRecord, RateLimitState, SubmitStatus


def record(row_id: str, *, alpha_hash: str | None = None, universe: str = "TOP3000") -> PayloadRecord:
    return PayloadRecord(
        row_id=row_id,
        alpha_hash=alpha_hash or f"hash-{row_id}",
        payload={
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY",
                "region": "USA",
                "universe": universe,
                "delay": 1,
                "language": "FASTEXPR",
            },
            "regular": f"rank(close) + {row_id}",
        },
    )


def read_summary(run_dir: Path) -> list[dict[str, str]]:
    with (run_dir / "summary.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FakeClient:
    def __init__(
        self,
        *,
        submit_actions: list[object] | None = None,
        poll_actions: list[object] | None = None,
        fetch_alpha_error: Exception | None = None,
        fetch_recordset_error: Exception | None = None,
    ) -> None:
        self.submit_actions = list(submit_actions or [])
        self.poll_actions = list(poll_actions or [])
        self.submissions: list[dict | list] = []
        self.fetch_alpha_calls: list[str] = []
        self.fetch_recordset_calls: list[tuple[str, str]] = []
        self.fetch_alpha_error = fetch_alpha_error
        self.fetch_recordset_error = fetch_recordset_error
        self._next_sim = 0
        self._poll_bodies: dict[str, dict] = {}

    def submit(self, payload: dict | list) -> SubmitResult:
        self.submissions.append(payload)
        action = self.submit_actions.pop(0) if self.submit_actions else "accept"
        if isinstance(action, Exception):
            raise action
        if action == "reject":
            return SubmitResult(
                status_code=400,
                location="",
                body={"message": "multi submit rejected"},
                headers={},
                rate_limit=RateLimitState(None, None, None),
            )
        if action == "missing_location":
            return SubmitResult(
                status_code=201,
                location="",
                body={"id": "missing-location"},
                headers={},
                rate_limit=RateLimitState(None, None, None),
            )

        self._next_sim += 1
        location = f"/simulations/{self._next_sim}"
        count = len(payload) if isinstance(payload, list) else 1
        alpha_ids = [f"alpha-{self._next_sim}-{index}" for index in range(count)]
        self._poll_bodies[location] = (
            {"alpha": alpha_ids[0], "status": "COMPLETE"}
            if count == 1
            else {"alphas": [{"alpha": alpha_id} for alpha_id in alpha_ids], "status": "COMPLETE"}
        )
        return SubmitResult(
            status_code=201,
            location=location,
            body={"id": location.rsplit("/", 1)[-1]},
            headers={"Location": location},
            rate_limit=RateLimitState(None, None, None),
        )

    def poll(self, location: str, *, timeout_seconds: float) -> PollResult:
        action = self.poll_actions.pop(0) if self.poll_actions else "complete"
        if isinstance(action, Exception):
            raise action
        if isinstance(action, PollResult):
            return action
        if action == "poll_error":
            return PollResult(
                status=SubmitStatus.POLL_ERROR.value,
                body={"message": "simulation failed"},
                events=[{"body": {"message": "simulation failed"}}],
            )
        if action == "pending_timeout":
            return PollResult(
                status=SubmitStatus.PENDING_TIMEOUT.value,
                body={"progress": 0.5},
                events=[{"body": {"progress": 0.5}}],
            )
        return PollResult(
            status=SubmitStatus.COMPLETE.value,
            body=self._poll_bodies[location],
            events=[{"body": self._poll_bodies[location]}],
        )

    def fetch_alpha(self, alpha_id: str) -> dict:
        self.fetch_alpha_calls.append(alpha_id)
        if self.fetch_alpha_error is not None:
            raise self.fetch_alpha_error
        return {
            "id": alpha_id,
            "status": "UNSUBMITTED",
            "is": {
                "sharpe": 1.1,
                "fitness": 0.7,
                "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
            },
        }

    def fetch_recordset(self, alpha_id: str, recordset_name: str) -> dict:
        self.fetch_recordset_calls.append((alpha_id, recordset_name))
        if self.fetch_recordset_error is not None:
            raise self.fetch_recordset_error
        return {"alpha_id": alpha_id, "recordset": recordset_name, "rows": []}


def test_chunk_records_chunks_and_rejects_invalid_size() -> None:
    records = [record(str(index)) for index in range(5)]

    assert [[item.row_id for item in chunk] for chunk in chunk_records(records, 2)] == [
        ["0", "1"],
        ["2", "3"],
        ["4"],
    ]

    for size in (0, -1):
        try:
            list(chunk_records(records, size))
        except ValueError as exc:
            assert "greater than 0" in str(exc)
        else:
            raise AssertionError("invalid chunk size was accepted")


def test_auto_fallback_splits_8_to_4_then_singles_on_submit_reject(tmp_path) -> None:
    records = [record(str(index)) for index in range(8)]
    client = FakeClient(submit_actions=["reject", "reject", "accept", "accept", "accept", "accept", "accept"])
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size="auto", poll_timeout_seconds=1)

    assert [len(payload) if isinstance(payload, list) else 1 for payload in client.submissions] == [
        8,
        4,
        1,
        1,
        1,
        1,
        4,
    ]
    assert result["submitted"] == 8
    assert result["completed"] == 8


def test_fixed_4_falls_back_to_singles_on_submit_reject(tmp_path) -> None:
    records = [record(str(index)) for index in range(4)]
    client = FakeClient(submit_actions=["reject", "accept", "accept", "accept", "accept"])
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=4, poll_timeout_seconds=1)

    assert [len(payload) if isinstance(payload, list) else 1 for payload in client.submissions] == [
        4,
        1,
        1,
        1,
        1,
    ]
    assert result["completed"] == 4


def test_duplicates_are_skipped_without_client_submit(tmp_path) -> None:
    duplicate = record("dup", alpha_hash="same-hash")
    client = FakeClient()
    runner = BatchRunner(client, tmp_path / "run")
    runner.cache.record(alpha_hash="same-hash", alpha_id="existing-alpha", row_id="old", status="complete")

    result = runner.run([duplicate], batch_size="auto", poll_timeout_seconds=1)

    assert client.submissions == []
    assert result["skipped_duplicates"] == 1
    rows = read_summary(tmp_path / "run")
    assert rows[0]["status"] == SubmitStatus.SKIPPED_DUPLICATE.value
    assert rows[0]["alpha_id"] == "existing-alpha"


def test_repeated_hash_later_in_same_run_is_skipped_after_first_completion(tmp_path) -> None:
    records = [record("first", alpha_hash="same-hash"), record("second", alpha_hash="same-hash")]
    client = FakeClient()
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size="auto", poll_timeout_seconds=1)

    assert len(client.submissions) == 1
    assert result["submitted"] == 1
    assert result["completed"] == 1
    assert result["skipped_duplicates"] == 1
    rows = read_summary(tmp_path / "run")
    assert [row["status"] for row in rows] == [
        SubmitStatus.COMPLETE.value,
        SubmitStatus.SKIPPED_DUPLICATE.value,
    ]
    assert rows[1]["alpha_id"] == rows[0]["alpha_id"]


def test_incompatible_payloads_are_submitted_singly(tmp_path) -> None:
    records = [record("usa", universe="TOP3000"), record("other", universe="TOP1000")]
    client = FakeClient()
    runner = BatchRunner(client, tmp_path / "run")

    runner.run(records, batch_size=8, poll_timeout_seconds=1)

    assert len(client.submissions) == 2
    assert all(isinstance(payload, dict) for payload in client.submissions)


def test_complete_flow_writes_artifacts_recordsets_summary_and_cache(tmp_path) -> None:
    records = [record("r1")]
    client = FakeClient()
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=1, poll_timeout_seconds=1, recordsets=["pnl"])

    assert result == {
        "requested": 1,
        "submitted": 1,
        "skipped_duplicates": 0,
        "completed": 1,
        "failed": 0,
        "run_dir": str(tmp_path / "run"),
    }
    rows = read_summary(tmp_path / "run")
    assert rows[0]["status"] == SubmitStatus.COMPLETE.value
    assert rows[0]["alpha_id"].startswith("alpha-")
    submit_logs = list((tmp_path / "run" / "raw").glob("submit-*.jsonl"))
    poll_logs = list((tmp_path / "run" / "raw").glob("poll-*.jsonl"))
    assert submit_logs and read_jsonl(submit_logs[0])
    assert poll_logs and read_jsonl(poll_logs[0])
    assert list((tmp_path / "run" / "alphas").glob("alpha-*.json"))
    assert list((tmp_path / "run" / "recordsets").glob("alpha-*/*.json"))
    assert runner.cache.lookup("hash-r1")["alpha_id"] == rows[0]["alpha_id"]


def test_poll_error_pending_timeout_and_submit_error_go_to_retry_queue(tmp_path) -> None:
    records = [record("poll"), record("timeout"), record("submit")]
    client = FakeClient(
        submit_actions=["accept", "accept", "reject"],
        poll_actions=["poll_error", "pending_timeout"],
    )
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=1, poll_timeout_seconds=1)

    assert result["failed"] == 3
    retry_rows = read_jsonl(tmp_path / "run" / "retry_queue.jsonl")
    assert [row["status"] for row in retry_rows] == [
        SubmitStatus.POLL_ERROR.value,
        SubmitStatus.PENDING_TIMEOUT.value,
        SubmitStatus.SUBMIT_ERROR.value,
    ]


def test_client_exceptions_do_not_crash_whole_run_and_write_retry(tmp_path) -> None:
    records = [record("bad"), record("good")]
    client = FakeClient(submit_actions=[RuntimeError("network down"), "accept"])
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=1, poll_timeout_seconds=1)

    assert result["completed"] == 1
    assert result["failed"] == 1
    retry_rows = read_jsonl(tmp_path / "run" / "retry_queue.jsonl")
    assert retry_rows[0]["row_id"] == "bad"
    assert retry_rows[0]["status"] == SubmitStatus.EXCEPTION.value
    assert "network down" in retry_rows[0]["error"]


def test_fetch_alpha_exception_is_preserved_in_retry_without_losing_completion(tmp_path) -> None:
    records = [record("r1")]
    client = FakeClient(fetch_alpha_error=RuntimeError("detail unavailable"))
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=1, poll_timeout_seconds=1)

    assert result["completed"] == 1
    rows = read_summary(tmp_path / "run")
    assert rows[0]["status"] == SubmitStatus.COMPLETE.value
    assert "detail unavailable" in rows[0]["error"]
    retry_rows = read_jsonl(tmp_path / "run" / "retry_queue.jsonl")
    assert retry_rows[0]["status"] == SubmitStatus.EXCEPTION.value
    assert runner.cache.lookup("hash-r1")["alpha_id"] == rows[0]["alpha_id"]


def test_missing_alpha_id_is_failure_with_retry_and_not_cached(tmp_path) -> None:
    records = [record("r1")]
    client = FakeClient(poll_actions=[PollResult(status="complete", body={"status": "COMPLETE"}, events=[])])
    runner = BatchRunner(client, tmp_path / "run")

    result = runner.run(records, batch_size=1, poll_timeout_seconds=1)

    assert result["completed"] == 0
    assert result["failed"] == 1
    rows = read_summary(tmp_path / "run")
    assert rows[0]["status"] == SubmitStatus.POLL_ERROR.value
    assert runner.cache.lookup("hash-r1") is None
    retry_rows = read_jsonl(tmp_path / "run" / "retry_queue.jsonl")
    assert retry_rows[0]["row_id"] == "r1"


def test_extract_alpha_ids_accepts_common_poll_shapes() -> None:
    assert extract_alpha_ids({"alpha": "a1"}) == ["a1"]
    assert extract_alpha_ids({"alpha_id": "a2"}) == ["a2"]
    assert extract_alpha_ids({"alphaId": "a3"}) == ["a3"]
    assert extract_alpha_ids([{"alpha": "a4"}, {"alpha_id": "a5"}]) == ["a4", "a5"]
    assert extract_alpha_ids({"results": [{"alpha": {"id": "a6"}}, {"alphaId": "a7"}]}) == [
        "a6",
        "a7",
    ]
