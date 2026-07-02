from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

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
    return int(float(value))


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
        return SubmitResult(
            status_code=response.status_code,
            location=response.headers.get("Location", ""),
            body=_read_body(response),
            headers=dict(response.headers),
            rate_limit=parse_rate_limit(response.headers),
        )

    def poll(self, location: str, *, timeout_seconds: float) -> PollResult:
        deadline = time.monotonic() + timeout_seconds
        events: list[dict[str, Any]] = []
        while True:
            response = self.session.get(location, timeout=60)
            body = _read_body(response)
            retry_after = response.headers.get("Retry-After")
            events.append(
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": body,
                }
            )
            if retry_after and float(retry_after) > 0:
                if time.monotonic() >= deadline:
                    return PollResult(status="pending_timeout", body=body, events=events)
                time.sleep(min(float(retry_after), self.max_sleep_seconds))
                continue
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
