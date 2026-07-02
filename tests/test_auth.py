from __future__ import annotations

import json
import stat

import pytest
import requests

from brain_sim.auth import BrainAuth, BrainAuthError, load_credentials
from brain_sim.notify import MemoryNotifier


class FailingNotifier:
    def send_login_link(self, to_email: str, url: str) -> None:
        raise RuntimeError("smtp unavailable")


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


def test_login_accepts_persona_header_variants(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/authentication",
        status_code=401,
        headers={
            "WWW-Authenticate": 'Persona realm="brain"',
            "Location": "/authentication/persona?inquiry=inq_123",
        },
        json={"detail": "persona required"},
    )

    auth = BrainAuth(session=session)
    challenge = auth.login("u@example.com", "secret")

    assert challenge.url == "https://api.worldquantbrain.com/authentication/persona?inquiry=inq_123"


def test_login_accepts_persona_from_multiple_challenges(requests_mock) -> None:
    session = requests.Session()
    requests_mock.post(
        "https://api.worldquantbrain.com/authentication",
        status_code=401,
        headers={
            "WWW-Authenticate": "Basic, persona",
            "Location": "/authentication/persona?inquiry=inq_123",
        },
        json={"detail": "persona required"},
    )

    auth = BrainAuth(session=session)
    challenge = auth.login("u@example.com", "secret")

    assert challenge.url == "https://api.worldquantbrain.com/authentication/persona?inquiry=inq_123"


def test_notifier_failure_still_returns_challenge(requests_mock) -> None:
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

    auth = BrainAuth(session=session, notifier=FailingNotifier())
    challenge = auth.login("u@example.com", "secret", notify_email="me@example.com")

    assert challenge.url == "https://api.worldquantbrain.com/authentication/persona?inquiry=inq_123"
    assert "Notification failed: smtp unavailable" in challenge.message


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
    cookie_path = tmp_path / "cookies.json"
    saved = json.loads(cookie_path.read_text(encoding="utf-8"))
    assert saved["cookies"] == [
        {
            "name": "t",
            "value": "jwt-value",
            "domain": "api.worldquantbrain.com",
            "path": "/",
            "secure": True,
            "expires": None,
        }
    ]
    assert stat.S_IMODE(cookie_path.stat().st_mode) == 0o600


def test_load_saved_cookies_reloads_domain_scoped_cookie(tmp_path) -> None:
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "t",
                        "value": "jwt-value",
                        "domain": "api.worldquantbrain.com",
                        "path": "/",
                        "secure": True,
                        "expires": None,
                    },
                    {
                        "name": "ignore",
                        "value": "not-worldquant",
                        "domain": "example.com",
                        "path": "/",
                        "secure": False,
                        "expires": None,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    session = requests.Session()

    auth = BrainAuth(session=session, cookie_path=cookie_path)

    assert auth.load_saved_cookies() is True
    cookies = list(session.cookies)
    assert len(cookies) == 1
    assert cookies[0].name == "t"
    assert cookies[0].value == "jwt-value"
    assert cookies[0].domain == "api.worldquantbrain.com"
    assert cookies[0].path == "/"
    assert cookies[0].secure is True


def test_load_saved_cookies_supports_legacy_cookie_cache(tmp_path) -> None:
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(json.dumps({"cookies": {"t": "jwt-value"}}), encoding="utf-8")
    session = requests.Session()

    auth = BrainAuth(session=session, cookie_path=cookie_path)

    assert auth.load_saved_cookies() is True
    cookies = list(session.cookies)
    assert len(cookies) == 1
    assert cookies[0].name == "t"
    assert cookies[0].value == "jwt-value"
    assert cookies[0].domain == "api.worldquantbrain.com"
    assert cookies[0].path == "/"
    assert cookies[0].secure is True
