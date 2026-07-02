from __future__ import annotations

import csv
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


SUMMARY_FIELDS = [
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": str(value)}
    return str(value)


def _json_dumps(payload: Any, *, pretty: bool) -> str:
    kwargs = {
        "allow_nan": False,
        "ensure_ascii": False,
        "sort_keys": True,
    }
    if pretty:
        kwargs["indent"] = 2
    return json.dumps(_to_jsonable(payload), **kwargs)


def _empty_summary_fragment() -> dict[str, Any]:
    return {
        "alpha_id": "",
        "sharpe": "",
        "fitness": "",
        "returns": "",
        "turnover": "",
        "drawdown": "",
        "margin": "",
        "longCount": "",
        "shortCount": "",
        "failed_checks": "",
        "warning_checks": "",
        "pending_checks": "",
    }


def summarize_alpha(alpha_body: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(alpha_body, dict):
        return _empty_summary_fragment()

    metrics = alpha_body.get("is")
    if not isinstance(metrics, dict):
        metrics = {}
    checks = metrics.get("checks")
    if not isinstance(checks, list):
        checks = []

    failed: list[str] = []
    warnings: list[str] = []
    pending: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name", "")).strip()
        if not name:
            continue
        result = str(check.get("result", "")).upper()
        if result == "FAIL":
            failed.append(name)
        elif result == "WARNING":
            warnings.append(name)
        elif result == "PENDING":
            pending.append(name)

    return {
        "alpha_id": alpha_body.get("id", ""),
        "status": alpha_body.get("status", ""),
        "sharpe": metrics.get("sharpe", ""),
        "fitness": metrics.get("fitness", ""),
        "returns": metrics.get("returns", ""),
        "turnover": metrics.get("turnover", ""),
        "drawdown": metrics.get("drawdown", ""),
        "margin": metrics.get("margin", ""),
        "longCount": metrics.get("longCount", ""),
        "shortCount": metrics.get("shortCount", ""),
        "failed_checks": ";".join(failed),
        "warning_checks": ";".join(warnings),
        "pending_checks": ";".join(pending),
    }


class RunStore:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for dirname in ("raw", "alphas", "recordsets"):
            (self.run_dir / dirname).mkdir(exist_ok=True)

    def write_manifest(self, payload: dict[str, Any]) -> None:
        self.write_json("manifest.json", payload)

    def write_json(self, relative_path: str | Path, payload: Any) -> Path:
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dumps(payload, pretty=True) + "\n", encoding="utf-8")
        return path

    def append_jsonl(
        self,
        relative_path: str | Path,
        payload: Any,
        *,
        row_id: str | None = None,
        status: str | None = None,
    ) -> Path:
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        event = _to_jsonable(payload)
        if isinstance(event, dict):
            event.setdefault("timestamp", _utc_now())
            if row_id is not None:
                event.setdefault("row_id", row_id)
            if status is not None:
                event.setdefault("status", status)
        else:
            event = {
                "timestamp": _utc_now(),
                "row_id": row_id or "",
                "status": status or "",
                "body": event,
            }
        with path.open("a", encoding="utf-8") as f:
            f.write(_json_dumps(event, pretty=False) + "\n")
        return path

    def append_raw_event(
        self,
        event_name: str,
        payload: Any,
        *,
        row_id: str | None = None,
        status: str | None = None,
    ) -> Path:
        return self.append_jsonl(
            Path("raw") / f"{event_name}.jsonl",
            payload,
            row_id=row_id,
            status=status,
        )

    def write_summary(self, rows: Iterable[dict[str, Any]]) -> Path:
        path = self.run_dir / "summary.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            for row in rows:
                clean = _to_jsonable(row)
                if not isinstance(clean, dict):
                    clean = {}
                writer.writerow({key: clean.get(key, "") for key in SUMMARY_FIELDS})
        return path

    def write_alpha_detail(self, alpha_id: str, alpha_body: Any) -> Path:
        safe_alpha_id = self._safe_filename(alpha_id)
        return self.write_json(Path("alphas") / f"{safe_alpha_id}.json", alpha_body)

    def write_recordset(self, alpha_id: str, recordset_name: str, payload: Any) -> Path:
        safe_alpha_id = self._safe_filename(alpha_id)
        safe_recordset = self._safe_filename(recordset_name)
        if isinstance(payload, (dict, list)):
            body = payload
        else:
            body = {"raw_text": _to_jsonable(payload)}
        return self.write_json(Path("recordsets") / safe_alpha_id / f"{safe_recordset}.json", body)

    def write_retry_queue(self, rows: Iterable[dict[str, Any]]) -> Path:
        path = self.run_dir / "retry_queue.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                clean = _to_jsonable(row)
                if isinstance(clean, dict):
                    clean.setdefault("timestamp", _utc_now())
                f.write(_json_dumps(clean, pretty=False) + "\n")
        return path

    @staticmethod
    def _safe_filename(value: str) -> str:
        text = value.strip() or "unknown"
        return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
