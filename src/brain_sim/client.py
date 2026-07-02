from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

from .auth import API_BASE
from .models import RateLimitState


@dataclass(frozen=True)
class SubmitResult:
    status_code: int
    location: str
    body: Any
    headers: dict[str, str]
    rate_limit: RateLimitState


@dataclass(frozen=True)
class PollResult:
    status: str
    body: Any
    events: list[dict[str, Any]] = field(default_factory=list)


def _read_body(response: requests.Response) -> Any:
    if not response.text:
        return None
    try:
        return response.json()
    except ValueError:
        return {"raw_text": response.text}


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    if value in (None, ""):
        return None
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return seconds
        return None
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (retry_at - current).total_seconds())


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimitState:
    lowered = {key.lower(): value for key, value in headers.items()}
    return RateLimitState(
        limit=_optional_int(lowered.get("x-ratelimit-limit")),
        remaining=_optional_int(lowered.get("x-ratelimit-remaining")),
        reset_seconds=_optional_int(lowered.get("x-ratelimit-reset")),
    )


def _terminal_status(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None

    status = str(body.get("status", "")).upper()
    if status in {"COMPLETE", "COMPLETED", "SUCCESS", "DONE"}:
        return "complete"
    if status in {"FAILED", "FAILURE", "ERROR"} or "error" in body:
        return "poll_error"
    if body.get("alpha") or body.get("alpha_id") or body.get("alphaId"):
        return "complete"
    return None


class BrainClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_base: str = API_BASE,
        max_sleep_seconds: float = 30.0,
        request_timeout_seconds: float = 60.0,
        min_poll_interval_seconds: float = 1.0,
    ) -> None:
        self.session = session or requests.Session()
        self.api_base = api_base.rstrip("/")
        self.max_sleep_seconds = max_sleep_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.min_poll_interval_seconds = min_poll_interval_seconds

    def _url(self, path_or_url: str) -> str:
        parsed = urlparse(path_or_url)
        if parsed.scheme and parsed.netloc:
            return path_or_url
        return f"{self.api_base}/{path_or_url.lstrip('/')}"

    def submit(self, payload: dict[str, Any] | list[dict[str, Any]]) -> SubmitResult:
        response = self.session.post(
            self._url("simulations"),
            json=payload,
            timeout=self.request_timeout_seconds,
        )
        location = response.headers.get("Location", "")
        return SubmitResult(
            status_code=response.status_code,
            location=self._url(location) if location else "",
            body=_read_body(response),
            headers=dict(response.headers),
            rate_limit=parse_rate_limit(response.headers),
        )

    def poll(self, location: str, *, timeout_seconds: float) -> PollResult:
        deadline = time.monotonic() + timeout_seconds
        url = self._url(location)
        events: list[dict[str, Any]] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return PollResult(status="pending_timeout", body=None, events=events)
            request_timeout = min(self.request_timeout_seconds, remaining)
            try:
                response = self.session.get(url, timeout=request_timeout)
            except requests.Timeout as exc:
                events.append({"exception": type(exc).__name__, "message": str(exc)})
                return PollResult(status="pending_timeout", body=None, events=events)
            body = _read_body(response)
            retry_after = response.headers.get("Retry-After")
            events.append(
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": body,
                }
            )
            if time.monotonic() > deadline:
                return PollResult(status="pending_timeout", body=body, events=events)
            if not response.ok:
                return PollResult(status="poll_error", body=body, events=events)
            status = _terminal_status(body)
            if status:
                return PollResult(status=status, body=body, events=events)

            retry_delay = parse_retry_after(retry_after)
            if retry_delay is None or retry_delay <= 0:
                retry_delay = self.min_poll_interval_seconds
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return PollResult(status="pending_timeout", body=body, events=events)
            sleep_seconds = min(max(retry_delay, 0.0), self.max_sleep_seconds, remaining)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if time.monotonic() >= deadline:
                return PollResult(status="pending_timeout", body=body, events=events)

    def fetch_alpha(self, alpha_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"alphas/{alpha_id}"),
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        body = _read_body(response)
        if not isinstance(body, dict):
            raise ValueError(f"Expected alpha response object for {alpha_id}")
        return body

    def fetch_recordset(self, alpha_id: str, recordset_name: str) -> Any:
        url = self._url(f"alphas/{alpha_id}/recordsets/{recordset_name}")
        response = self.session.get(url, timeout=self.request_timeout_seconds)
        response.raise_for_status()
        return _read_body(response)
