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
    clock_values = iter([0.0, 0.9, 1.0])
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
    clock_values = iter([0.0, 1.1])
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
