from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import requests

import brain_sim.client as client_module
from brain_sim.client import BrainClient, parse_rate_limit, parse_retry_after


def test_parse_rate_limit_accepts_lowercase_headers() -> None:
    headers = {
        "x-ratelimit-limit": "1000",
        "x-ratelimit-remaining": "987",
        "x-ratelimit-reset": "3600",
    }

    state = parse_rate_limit(headers)

    assert state.limit == 1000
    assert state.remaining == 987
    assert state.reset_seconds == 3600


def test_parse_rate_limit_ignores_malformed_headers() -> None:
    headers = {
        "X-Ratelimit-Limit": "bad",
        "X-Ratelimit-Remaining": "",
        "X-Ratelimit-Reset": "12x",
    }

    state = parse_rate_limit(headers)

    assert state.limit is None
    assert state.remaining is None
    assert state.reset_seconds is None


def test_parse_retry_after_accepts_http_date() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    retry_at = now + timedelta(seconds=5)
    header = format_datetime(retry_at, usegmt=True)

    assert parse_retry_after(header, now=now) == 5


def test_parse_retry_after_returns_none_for_invalid_value() -> None:
    assert parse_retry_after("not-a-date") is None


def test_parse_retry_after_returns_none_for_non_finite_numeric_values() -> None:
    assert parse_retry_after("NaN") is None
    assert parse_retry_after("Infinity") is None


def test_submit_simulation_returns_location_and_headers(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/simulations",
        status_code=201,
        headers={
            "Location": "https://api.worldquantbrain.com/simulations/sim-1",
            "X-Ratelimit-Limit": "1000",
            "X-Ratelimit-Remaining": "999",
            "X-Ratelimit-Reset": "80000",
        },
        json={"id": "sim-1"},
    )
    client = BrainClient(session=session)

    result = client.submit({"type": "REGULAR", "settings": {}, "regular": "close"})

    assert result.status_code == 201
    assert result.location == "https://api.worldquantbrain.com/simulations/sim-1"
    assert result.body == {"id": "sim-1"}
    assert result.headers["Location"] == "https://api.worldquantbrain.com/simulations/sim-1"
    assert result.rate_limit.remaining == 999


def test_submit_normalizes_relative_location(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/simulations",
        status_code=201,
        headers={"Location": "/simulations/123"},
        json={"id": "123"},
    )
    client = BrainClient(session=session)

    result = client.submit({"type": "REGULAR", "settings": {}, "regular": "close"})

    assert result.location == "https://api.worldquantbrain.com/simulations/123"


def test_submit_preserves_non_json_body(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/simulations",
        status_code=202,
        text="accepted",
    )
    client = BrainClient(session=session)

    result = client.submit({"type": "REGULAR", "settings": {}, "regular": "close"})

    assert result.body == {"raw_text": "accepted"}


def test_poll_waits_until_retry_after_disappears(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "0.01"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert result.body["alpha"] == "alpha-1"
    assert len(result.events) == 2


def test_poll_accepts_http_date_retry_after(requests_mock) -> None:
    session = requests.Session()
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=0.01)
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {
                "status_code": 200,
                "headers": {"Retry-After": format_datetime(retry_at, usegmt=True)},
                "json": {"progress": 0.2},
            },
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert len(result.events) == 2


def test_poll_keeps_pending_response_without_terminal_body_pending(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=200,
        json={"progress": 0.2},
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01, min_poll_interval_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=0.01)

    assert result.status == "pending_timeout"
    assert result.body == {"progress": 0.2}


def test_poll_zero_retry_after_does_not_mark_pending_body_complete(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "0"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01, min_poll_interval_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert len(result.events) == 2


def test_poll_negative_retry_after_does_not_mark_pending_body_complete(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "-1"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01, min_poll_interval_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert len(result.events) == 2


def test_poll_past_retry_after_does_not_mark_pending_body_complete(requests_mock) -> None:
    session = requests.Session()
    retry_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {
                "status_code": 200,
                "headers": {"Retry-After": format_datetime(retry_at, usegmt=True)},
                "json": {"progress": 0.2},
            },
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.01, min_poll_interval_seconds=0.01)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert len(result.events) == 2


def test_poll_failed_terminal_status_is_poll_error(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=200,
        json={"status": "FAILED", "message": "bad expression"},
    )
    client = BrainClient(session=session)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "poll_error"
    assert result.body["message"] == "bad expression"


def test_poll_http_error_is_poll_error_and_preserves_raw_body(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=500,
        text="server unavailable",
    )
    client = BrainClient(session=session)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "poll_error"
    assert result.body == {"raw_text": "server unavailable"}


def test_poll_returns_timeout_when_retry_sleep_crosses_deadline(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "0.02"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=0.02)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=0.001)

    assert result.status == "pending_timeout"
    assert result.body == {"progress": 0.2}
    assert len(result.events) == 1


def test_poll_caps_sleep_to_remaining_timeout(requests_mock, monkeypatch) -> None:
    clock_values = iter([0.0, 0.0, 0.0, 0.9, 1.0])
    sleep_values: list[float] = []
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(client_module.time, "sleep", sleep_values.append)
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "10"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, max_sleep_seconds=30)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=1)

    assert result.status == "pending_timeout"
    assert sleep_values == [0.09999999999999998]
    assert len(result.events) == 1


def test_poll_rejects_completion_after_deadline_elapsed(requests_mock, monkeypatch) -> None:
    clock_values = iter([0.0, 0.0, 1.1])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock_values))
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=200,
        json={"alpha": "alpha-1", "status": "COMPLETE"},
    )
    client = BrainClient(session=session)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=1)

    assert result.status == "pending_timeout"
    assert result.body == {"alpha": "alpha-1", "status": "COMPLETE"}
    assert len(result.events) == 1


def test_poll_treats_invalid_retry_after_as_no_retry_delay(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=200,
        headers={"Retry-After": "not-a-date"},
        json={"alpha": "alpha-1", "status": "COMPLETE"},
    )
    client = BrainClient(session=session)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert result.body["alpha"] == "alpha-1"
    assert len(result.events) == 1


def test_poll_non_finite_retry_after_uses_minimum_interval(requests_mock, monkeypatch) -> None:
    sleep_values: list[float] = []
    monkeypatch.setattr(client_module.time, "sleep", sleep_values.append)
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        [
            {"status_code": 200, "headers": {"Retry-After": "NaN"}, "json": {"progress": 0.2}},
            {"status_code": 200, "json": {"alpha": "alpha-1", "status": "COMPLETE"}},
        ],
    )
    client = BrainClient(session=session, min_poll_interval_seconds=0.25)

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert sleep_values == [0.25]
    assert len(result.events) == 2


def test_poll_normalizes_relative_location_input(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/simulations/sim-1",
        status_code=200,
        json={"alpha": "alpha-1", "status": "COMPLETE"},
    )
    client = BrainClient(session=session)

    result = client.poll("/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert result.body["alpha"] == "alpha-1"


def test_poll_normalizes_relative_location_against_path_prefixed_api_base(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://proxy.example.com/brain/api/simulations/sim-1",
        status_code=200,
        json={"alpha": "alpha-1", "status": "COMPLETE"},
    )
    client = BrainClient(session=session, api_base="https://proxy.example.com/brain/api")

    result = client.poll("/simulations/sim-1", timeout_seconds=2)

    assert result.status == "complete"
    assert result.body["alpha"] == "alpha-1"


def test_poll_caps_request_timeout_to_remaining_deadline(monkeypatch) -> None:
    captured_timeouts: list[float] = []

    class TimeoutSession:
        def get(self, url: str, *, timeout: float) -> None:
            captured_timeouts.append(timeout)
            raise requests.Timeout("slow")

    monkeypatch.setattr(client_module.time, "monotonic", lambda: 10.0)
    client = BrainClient(session=TimeoutSession(), request_timeout_seconds=60)  # type: ignore[arg-type]

    result = client.poll("https://api.worldquantbrain.com/simulations/sim-1", timeout_seconds=5)

    assert result.status == "pending_timeout"
    assert captured_timeouts == [5]


def test_fetch_alpha_returns_json_object(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/alphas/alpha-1",
        json={"id": "alpha-1", "is": {"sharpe": 1.2}},
    )
    client = BrainClient(session=session)

    assert client.fetch_alpha("alpha-1") == {"id": "alpha-1", "is": {"sharpe": 1.2}}


def test_fetch_recordset_preserves_non_json_body(requests_mock) -> None:
    session = requests.Session()
    requests_mock.get(
        "https://api.worldquantbrain.com/alphas/alpha-1/recordsets/pnl",
        text="date,pnl\n2026-01-01,1.0",
    )
    client = BrainClient(session=session)

    assert client.fetch_recordset("alpha-1", "pnl") == {"raw_text": "date,pnl\n2026-01-01,1.0"}
