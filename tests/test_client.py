from __future__ import annotations

import requests

import brain_sim.client as client_module
from brain_sim.client import BrainClient, parse_rate_limit


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
