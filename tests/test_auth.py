from __future__ import annotations

import json

import pytest
import requests

from brain_sim.auth import BrainAuth, BrainAuthError, load_credentials
from brain_sim.notify import MemoryNotifier


def test_load_credentials_accepts_list_file(tmp_path) -> None:
    path = tmp_path / "creds.json"
    path.write_text(json.dumps(["u@example.com", "secret"]), encoding="utf-8")

    assert load_credentials(path) == ("u@example.com", "secret")


def test_login_returns_persona_challenge_and_notifies(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/authentication",
        status_code=401,
        headers={
            "WWW-Authenticate": "persona",
            "Location": "/authentication/persona?inquiry=inq_123",
        },
        json={"detail": "persona required"},
    )
    notifier = MemoryNotifier()

    auth = BrainAuth(session=session, notifier=notifier)
    challenge = auth.login("u@example.com", "secret", notify_email="me@example.com")

    assert challenge.url == "https://api.worldquantbrain.com/authentication/persona?inquiry=inq_123"
    assert notifier.sent_messages == [
        {
            "to_email": "me@example.com",
            "subject": "WorldQuant BRAIN login verification",
            "body": "Open this WorldQuant BRAIN verification link: https://api.worldquantbrain.com/authentication/persona?inquiry=inq_123",
        }
    ]


def test_login_raises_for_invalid_credentials(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/authentication",
        status_code=401,
        headers={"WWW-Authenticate": "Basic"},
        json={"detail": "INVALID_CREDENTIALS"},
    )

    auth = BrainAuth(session=session)

    with pytest.raises(BrainAuthError, match="Authentication failed"):
        auth.login("u@example.com", "bad")


def test_login_success_saves_cookie_file(requests_mock, tmp_path) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/authentication",
        status_code=201,
        headers={"Set-Cookie": "t=jwt-value; Path=/; secure"},
        json={"user": {"id": "NW123"}, "token": {"expiry": 14400}, "permissions": ["MULTI_SIMULATION"]},
    )

    auth = BrainAuth(session=session, cookie_path=tmp_path / "cookies.json")
    result = auth.login("u@example.com", "secret")

    assert result is None
    saved = json.loads((tmp_path / "cookies.json").read_text(encoding="utf-8"))
    assert saved["cookies"]["t"] == "jwt-value"
