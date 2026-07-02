from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Sequence

from .cache import SimulationCache
from .models import PayloadRecord, SubmitStatus
from .results import RunStore, summarize_alpha


BatchSize = Literal[1, 4, 8, "auto"]
_COMPATIBILITY_SETTING_KEYS = ("instrumentType", "region", "universe", "delay", "language")
_SUCCESS_STATUSES = {"complete", "completed", "success", "done"}
_RETRY_STATUSES = {
    SubmitStatus.SUBMIT_ERROR.value,
    SubmitStatus.POLL_ERROR.value,
    SubmitStatus.PENDING_TIMEOUT.value,
    SubmitStatus.EXCEPTION.value,
}


def chunk_records(records: Iterable[PayloadRecord], size: int) -> Iterator[list[PayloadRecord]]:
    if size <= 0:
        raise ValueError("chunk size must be greater than 0")

    chunk: list[PayloadRecord] = []
    for record in records:
        chunk.append(record)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def iter_allowed_batch_chunks(records: Iterable[PayloadRecord], max_size: int) -> Iterator[list[PayloadRecord]]:
    if max_size not in {1, 4, 8}:
        raise ValueError("max_size must be 1, 4, or 8")

    remaining = list(records)
    if max_size == 1:
        for record in remaining:
            yield [record]
        return

    if max_size == 8:
        while len(remaining) >= 8:
            yield remaining[:8]
            remaining = remaining[8:]

    while len(remaining) >= 4 and max_size >= 4:
        yield remaining[:4]
        remaining = remaining[4:]

    for record in remaining:
        yield [record]


class BatchRunner:
    def __init__(self, client: Any, run_dir: str | Path, cache_path: str | Path | None = None) -> None:
        self.client = client
        self.store = RunStore(run_dir)
        self.cache = SimulationCache(cache_path or self.store.run_dir / "simulation_cache.sqlite")

    def run(
        self,
        records: Iterable[PayloadRecord],
        *,
        batch_size: BatchSize,
        poll_timeout_seconds: float,
        recordsets: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if batch_size not in {1, 4, 8, "auto"}:
            raise ValueError("batch_size must be 1, 4, 8, or 'auto'")

        requested_records = list(records)
        requested_recordsets = list(recordsets or [])
        summary_rows: list[dict[str, Any]] = []
        retry_rows: list[dict[str, Any]] = []
        submitted_count = 0
        attempted_hashes: set[str] = set()

        records_to_submit: list[PayloadRecord] = []
        for record in requested_records:
            cached = self.cache.lookup(record.alpha_hash)
            if cached is not None:
                summary_rows.append(
                    self._summary_row(
                        record,
                        status=SubmitStatus.SKIPPED_DUPLICATE.value,
                        alpha_id=str(cached.get("alpha_id", "")),
                    )
                )
            else:
                records_to_submit.append(record)

        for compatible_run in self._compatible_runs(records_to_submit):
            if batch_size == "auto":
                for chunk in iter_allowed_batch_chunks(compatible_run, 8):
                    chunk = self._skip_cached(chunk, summary_rows, retry_rows, attempted_hashes)
                    if not chunk:
                        continue
                    submitted_count += self._process_auto_chunk(
                        chunk,
                        poll_timeout_seconds=poll_timeout_seconds,
                        recordsets=requested_recordsets,
                        summary_rows=summary_rows,
                        retry_rows=retry_rows,
                        attempted_hashes=attempted_hashes,
                    )
            elif batch_size == 1:
                for record in compatible_run:
                    pending = self._skip_cached([record], summary_rows, retry_rows, attempted_hashes)
                    if not pending:
                        continue
                    submitted_count += self._process_terminal_attempt(
                        pending,
                        poll_timeout_seconds=poll_timeout_seconds,
                        recordsets=requested_recordsets,
                        summary_rows=summary_rows,
                        retry_rows=retry_rows,
                        attempted_hashes=attempted_hashes,
                    )
            else:
                for chunk in iter_allowed_batch_chunks(compatible_run, batch_size):
                    chunk = self._skip_cached(chunk, summary_rows, retry_rows, attempted_hashes)
                    if not chunk:
                        continue
                    submitted_count += self._process_auto_chunk(
                        chunk,
                        poll_timeout_seconds=poll_timeout_seconds,
                        recordsets=requested_recordsets,
                        summary_rows=summary_rows,
                        retry_rows=retry_rows,
                        attempted_hashes=attempted_hashes,
                    )

        self.store.write_summary(summary_rows)
        self.store.write_retry_queue(retry_rows)

        completed = sum(1 for row in summary_rows if row.get("status") == SubmitStatus.COMPLETE.value)
        skipped = sum(
            1 for row in summary_rows if row.get("status") == SubmitStatus.SKIPPED_DUPLICATE.value
        )
        failed = len(retry_rows)
        return {
            "requested": len(requested_records),
            "submitted": submitted_count,
            "skipped_duplicates": skipped,
            "completed": completed,
            "failed": failed,
            "retry_queued": len(retry_rows),
            "run_dir": str(self.store.run_dir),
        }

    def _process_auto_chunk(
        self,
        records: list[PayloadRecord],
        *,
        poll_timeout_seconds: float,
        recordsets: Sequence[str],
        summary_rows: list[dict[str, Any]],
        retry_rows: list[dict[str, Any]],
        attempted_hashes: set[str],
    ) -> int:
        if len(records) == 1:
            return self._process_terminal_attempt(
                records,
                poll_timeout_seconds=poll_timeout_seconds,
                recordsets=recordsets,
                summary_rows=summary_rows,
                retry_rows=retry_rows,
                attempted_hashes=attempted_hashes,
            )

        attempt = self._attempt_submission(records, poll_timeout_seconds, recordsets)
        if not attempt["submission_failed"]:
            return self._finalize_attempt(
                records,
                attempt,
                summary_rows=summary_rows,
                retry_rows=retry_rows,
                attempted_hashes=attempted_hashes,
            )
        if not attempt.get("fallback_allowed", False):
            return self._finalize_attempt(
                records,
                attempt,
                summary_rows=summary_rows,
                retry_rows=retry_rows,
                attempted_hashes=attempted_hashes,
            )

        submitted = 0
        if len(records) <= 4:
            for record in records:
                submitted += self._process_terminal_attempt(
                    [record],
                    poll_timeout_seconds=poll_timeout_seconds,
                    recordsets=recordsets,
                    summary_rows=summary_rows,
                    retry_rows=retry_rows,
                    attempted_hashes=attempted_hashes,
                )
            return submitted

        for chunk in iter_allowed_batch_chunks(records, 4):
            chunk = self._skip_cached(chunk, summary_rows, retry_rows, attempted_hashes)
            if not chunk:
                continue
            four_attempt = self._attempt_submission(chunk, poll_timeout_seconds, recordsets)
            if (
                four_attempt["submission_failed"]
                and four_attempt.get("fallback_allowed", False)
                and len(chunk) > 1
            ):
                for record in chunk:
                    submitted += self._process_terminal_attempt(
                        [record],
                        poll_timeout_seconds=poll_timeout_seconds,
                        recordsets=recordsets,
                        summary_rows=summary_rows,
                        retry_rows=retry_rows,
                        attempted_hashes=attempted_hashes,
                    )
            else:
                submitted += self._finalize_attempt(
                    chunk,
                    four_attempt,
                    summary_rows=summary_rows,
                    retry_rows=retry_rows,
                    attempted_hashes=attempted_hashes,
                )
        return submitted

    def _process_terminal_attempt(
        self,
        records: list[PayloadRecord],
        *,
        poll_timeout_seconds: float,
        recordsets: Sequence[str],
        summary_rows: list[dict[str, Any]],
        retry_rows: list[dict[str, Any]],
        attempted_hashes: set[str],
    ) -> int:
        records = self._skip_cached(records, summary_rows, retry_rows, attempted_hashes)
        if not records:
            return 0
        attempt = self._attempt_submission(records, poll_timeout_seconds, recordsets)
        return self._finalize_attempt(
            records,
            attempt,
            summary_rows=summary_rows,
            retry_rows=retry_rows,
            attempted_hashes=attempted_hashes,
        )

    def _attempt_submission(
        self,
        records: list[PayloadRecord],
        poll_timeout_seconds: float,
        recordsets: Sequence[str],
    ) -> dict[str, Any]:
        payload = [record.payload for record in records] if len(records) > 1 else records[0].payload
        row_ids = [record.row_id for record in records]
        raw_context = {"row_ids": row_ids, "batch_size": len(records)}

        try:
            submit_result = self.client.submit(payload)
        except Exception as exc:  # noqa: BLE001 - client implementations surface transport errors differently.
            self.store.append_raw_event(
                "submit",
                {**raw_context, "payload": payload, "exception": exc},
                row_id=self._row_context(records),
                status=SubmitStatus.EXCEPTION.value,
            )
            return {
                "submission_failed": True,
                "fallback_allowed": False,
                "status": SubmitStatus.EXCEPTION.value,
                "error": f"{type(exc).__name__}: {exc}",
            }

        submit_status = self._submit_status(submit_result)
        self.store.append_raw_event(
            "submit",
            {**raw_context, "payload": payload, "result": submit_result},
            row_id=self._row_context(records),
            status=submit_status,
        )
        if submit_status != SubmitStatus.SUBMITTED.value:
            return {
                "submission_failed": True,
                "fallback_allowed": self._fallback_allowed(submit_result),
                "status": submit_status,
                "error": self._error_message(getattr(submit_result, "body", None), "submit failed"),
                "submit_result": submit_result,
            }

        location = str(getattr(submit_result, "location", "") or "")
        try:
            poll_result = self.client.poll(location, timeout_seconds=poll_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - preserve all client failures in artifacts.
            self.store.append_raw_event(
                "poll",
                {**raw_context, "location": location, "exception": exc},
                row_id=self._row_context(records),
                status=SubmitStatus.EXCEPTION.value,
            )
            return {
                "submission_failed": False,
                "submitted": len(records),
                "status": SubmitStatus.EXCEPTION.value,
                "error": f"{type(exc).__name__}: {exc}",
            }

        poll_status = self._normalize_poll_status(getattr(poll_result, "status", ""))
        events = getattr(poll_result, "events", []) or []
        for event in events:
            self.store.append_raw_event(
                "poll",
                {**raw_context, "location": location, "event": event},
                row_id=self._row_context(records),
                status=poll_status,
            )
        self.store.append_raw_event(
            "poll",
            {**raw_context, "location": location, "result": poll_result},
            row_id=self._row_context(records),
            status=poll_status,
        )

        return {
            "submission_failed": False,
            "submitted": len(records),
            "status": poll_status,
            "poll_body": getattr(poll_result, "body", None),
            "error": self._error_message(getattr(poll_result, "body", None), poll_status),
            "recordsets": list(recordsets),
        }

    def _finalize_attempt(
        self,
        records: list[PayloadRecord],
        attempt: dict[str, Any],
        *,
        summary_rows: list[dict[str, Any]],
        retry_rows: list[dict[str, Any]],
        attempted_hashes: set[str],
    ) -> int:
        for record in records:
            attempted_hashes.add(record.alpha_hash)

        status = str(attempt.get("status", SubmitStatus.EXCEPTION.value))
        if status == SubmitStatus.SUBMITTED.value:
            status = SubmitStatus.POLL_ERROR.value

        if status != SubmitStatus.COMPLETE.value:
            for record in records:
                row = self._summary_row(record, status=status, error=str(attempt.get("error", "")))
                summary_rows.append(row)
                retry_rows.append(self._retry_row(record, status=status, error=row["error"]))
            return int(attempt.get("submitted", 0) or 0)

        alpha_ids = extract_alpha_ids(attempt.get("poll_body"))
        if len(alpha_ids) != len(records):
            error = f"expected {len(records)} alpha id(s), got {len(alpha_ids)}"
            for record in records:
                row = self._summary_row(record, status=SubmitStatus.POLL_ERROR.value, error=error)
                summary_rows.append(row)
                retry_rows.append(self._retry_row(record, status=SubmitStatus.POLL_ERROR.value, error=error))
            return int(attempt.get("submitted", 0) or 0)

        for record, alpha_id in zip(records, alpha_ids):
            artifact_errors: list[str] = []
            alpha_body: Any = attempt.get("poll_body") if len(records) == 1 else {"alpha": alpha_id}
            try:
                alpha_body = self.client.fetch_alpha(alpha_id)
                self.store.write_alpha_detail(alpha_id, alpha_body)
            except Exception as exc:  # noqa: BLE001
                artifact_errors.append(f"fetch_alpha {type(exc).__name__}: {exc}")
                retry_rows.append(
                    self._retry_row(record, status=SubmitStatus.EXCEPTION.value, alpha_id=alpha_id, error=artifact_errors[-1])
                )

            for recordset_name in attempt.get("recordsets", []):
                try:
                    recordset_body = self.client.fetch_recordset(alpha_id, str(recordset_name))
                    self.store.write_recordset(alpha_id, str(recordset_name), recordset_body)
                except Exception as exc:  # noqa: BLE001
                    artifact_errors.append(f"fetch_recordset {recordset_name} {type(exc).__name__}: {exc}")
                    retry_rows.append(
                        self._retry_row(
                            record,
                            status=SubmitStatus.EXCEPTION.value,
                            alpha_id=alpha_id,
                            error=artifact_errors[-1],
                        )
                    )

            self.cache.record(
                alpha_hash=record.alpha_hash,
                alpha_id=alpha_id,
                row_id=record.row_id,
                status=SubmitStatus.COMPLETE.value,
            )
            summary_rows.append(
                self._summary_row(
                    record,
                    status=SubmitStatus.COMPLETE.value,
                    alpha_id=alpha_id,
                    alpha_body=alpha_body if isinstance(alpha_body, dict) else None,
                    error="; ".join(artifact_errors),
                )
            )

        return int(attempt.get("submitted", 0) or 0)

    def _compatible_runs(self, records: list[PayloadRecord]) -> Iterator[list[PayloadRecord]]:
        current: list[PayloadRecord] = []
        current_key: tuple[Any, ...] | None = None
        current_hashes: set[str] = set()
        for record in records:
            key = _compatibility_key(record)
            if current and (key != current_key or record.alpha_hash in current_hashes):
                yield current
                current = []
                current_hashes = set()
            current.append(record)
            current_hashes.add(record.alpha_hash)
            current_key = key
        if current:
            yield current

    def _skip_cached(
        self,
        records: list[PayloadRecord],
        summary_rows: list[dict[str, Any]],
        retry_rows: list[dict[str, Any]],
        attempted_hashes: set[str],
    ) -> list[PayloadRecord]:
        pending: list[PayloadRecord] = []
        for record in records:
            cached = self.cache.lookup(record.alpha_hash)
            if cached is None:
                if record.alpha_hash in attempted_hashes:
                    error = "duplicate payload already attempted in this run"
                    row = self._summary_row(record, status=SubmitStatus.SUBMIT_ERROR.value, error=error)
                    summary_rows.append(row)
                    retry_rows.append(
                        self._retry_row(record, status=SubmitStatus.SUBMIT_ERROR.value, error=error)
                    )
                    continue
                pending.append(record)
                continue
            summary_rows.append(
                self._summary_row(
                    record,
                    status=SubmitStatus.SKIPPED_DUPLICATE.value,
                    alpha_id=str(cached.get("alpha_id", "")),
                )
            )
        return pending

    def _summary_row(
        self,
        record: PayloadRecord,
        *,
        status: str,
        alpha_id: str = "",
        alpha_body: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        metrics = summarize_alpha(alpha_body)
        return {
            "row_id": record.row_id,
            "alpha_hash": record.alpha_hash,
            **metrics,
            "status": status,
            "alpha_id": alpha_id or metrics.get("alpha_id", ""),
            "error": error,
        }

    def _retry_row(
        self,
        record: PayloadRecord,
        *,
        status: str,
        error: str,
        alpha_id: str = "",
    ) -> dict[str, Any]:
        return {
            "row_id": record.row_id,
            "alpha_hash": record.alpha_hash,
            "alpha_id": alpha_id,
            "status": status,
            "error": error,
            "payload": record.payload,
            "metadata": record.metadata,
        }

    def _submit_status(self, submit_result: Any) -> str:
        status_code = getattr(submit_result, "status_code", None)
        location = str(getattr(submit_result, "location", "") or "")
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 300:
            return SubmitStatus.SUBMIT_ERROR.value
        if not location:
            return SubmitStatus.SUBMIT_ERROR.value
        return SubmitStatus.SUBMITTED.value

    def _fallback_allowed(self, submit_result: Any) -> bool:
        status_code = getattr(submit_result, "status_code", None)
        return isinstance(status_code, int) and status_code in {400, 413, 422}

    def _normalize_poll_status(self, status: Any) -> str:
        normalized = str(status or "").lower()
        if normalized in _SUCCESS_STATUSES:
            return SubmitStatus.COMPLETE.value
        if normalized == SubmitStatus.PENDING_TIMEOUT.value:
            return SubmitStatus.PENDING_TIMEOUT.value
        if normalized == SubmitStatus.POLL_ERROR.value:
            return SubmitStatus.POLL_ERROR.value
        if normalized == SubmitStatus.SUBMIT_ERROR.value:
            return SubmitStatus.SUBMIT_ERROR.value
        return SubmitStatus.POLL_ERROR.value

    def _error_message(self, body: Any, fallback: str) -> str:
        if isinstance(body, dict):
            for key in ("error", "message", "detail"):
                value = body.get(key)
                if value:
                    return str(value)
            raw_text = body.get("raw_text")
            if raw_text:
                return str(raw_text)
        return fallback

    def _row_context(self, records: list[PayloadRecord]) -> str:
        return records[0].row_id if len(records) == 1 else ",".join(record.row_id for record in records)


def _compatibility_key(record: PayloadRecord) -> tuple[Any, ...]:
    payload = record.payload
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    return tuple([payload.get("type"), *[settings.get(key) for key in _COMPATIBILITY_SETTING_KEYS]])


def extract_alpha_ids(body: Any) -> list[str]:
    ids: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value:
            ids.append(value)
        elif isinstance(value, dict):
            for key in ("alpha", "alpha_id", "alphaId"):
                if key in value:
                    add(value[key])
                    return
            if "id" in value and len(value) == 1:
                add(value["id"])
            for key in ("alphas", "alphaIds", "alpha_ids", "results", "result", "simulations", "children", "data"):
                if key in value:
                    add(value[key])
        elif isinstance(value, list):
            for item in value:
                add(item)

    add(_to_plain(body))
    return ids


def _to_plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    return value
