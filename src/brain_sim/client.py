from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urljoin

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
    except ValueError:
        return None


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
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


class BrainClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_base: str = API_BASE,
        max_sleep_seconds: float = 30.0,
    ) -> None:
        self.session = session or requests.Session()
        self.api_base = api_base.rstrip("/")
        self.max_sleep_seconds = max_sleep_seconds

    def submit(self, payload: dict[str, Any] | list[dict[str, Any]]) -> SubmitResult:
        response = self.session.post(f"{self.api_base}/simulations", json=payload, timeout=60)
        location = response.headers.get("Location", "")
        return SubmitResult(
            status_code=response.status_code,
            location=urljoin(response.url, location) if location else "",
            body=_read_body(response),
            headers=dict(response.headers),
            rate_limit=parse_rate_limit(response.headers),
        )

    def poll(self, location: str, *, timeout_seconds: float) -> PollResult:
        deadline = time.monotonic() + timeout_seconds
        url = urljoin(f"{self.api_base}/", location)
        events: list[dict[str, Any]] = []
        while True:
            response = self.session.get(url, timeout=60)
            body = _read_body(response)
            retry_after = response.headers.get("Retry-After")
            events.append(
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": body,
                }
            )
            retry_delay = parse_retry_after(retry_after)
            if retry_delay and retry_delay > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return PollResult(status="pending_timeout", body=body, events=events)
                time.sleep(min(retry_delay, self.max_sleep_seconds, remaining))
                if time.monotonic() >= deadline:
                    return PollResult(status="pending_timeout", body=body, events=events)
                continue
            if time.monotonic() > deadline:
                return PollResult(status="pending_timeout", body=body, events=events)
            if not response.ok:
                return PollResult(status="poll_error", body=body, events=events)
            return PollResult(status="complete", body=body, events=events)

    def fetch_alpha(self, alpha_id: str) -> dict[str, Any]:
        response = self.session.get(f"{self.api_base}/alphas/{alpha_id}", timeout=60)
        response.raise_for_status()
        return response.json()

    def fetch_recordset(self, alpha_id: str, recordset_name: str) -> Any:
        url = f"{self.api_base}/alphas/{alpha_id}/recordsets/{recordset_name}"
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return _read_body(response)
