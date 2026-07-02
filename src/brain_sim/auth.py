from __future__ import annotations

import json
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from .models import AuthChallenge
from .notify import Notifier


API_BASE = "https://api.worldquantbrain.com"


class BrainAuthError(RuntimeError):
    pass


def load_credentials(path: str | Path) -> tuple[str, str]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if isinstance(payload, list) and len(payload) >= 2:
        return str(payload[0]), str(payload[1])
    if isinstance(payload, dict) and payload.get("email") and payload.get("password"):
        return str(payload["email"]), str(payload["password"])
    raise BrainAuthError("Credential file must be a JSON list [email, password] or object with email/password.")


class BrainAuth:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_base: str = API_BASE,
        cookie_path: str | Path = ".brain_sim/cookies.json",
        notifier: Notifier | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.api_base = api_base.rstrip("/")
        self.cookie_path = Path(cookie_path)
        self.notifier = notifier

    def login(self, email: str, password: str, *, notify_email: str | None = None) -> AuthChallenge | None:
        response = self.session.post(
            f"{self.api_base}/authentication",
            auth=(email, password),
            timeout=60,
        )
        if response.status_code in (200, 201):
            self._save_cookies(response)
            return None

        if response.status_code == 401 and response.headers.get("WWW-Authenticate") == "persona":
            location = response.headers.get("Location", "")
            url = urljoin(response.url, location)
            challenge = AuthChallenge(
                url=url,
                www_authenticate="persona",
                message="WorldQuant BRAIN requires Persona verification.",
            )
            if notify_email and self.notifier:
                self.notifier.send_login_link(notify_email, url)
            return challenge

        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise BrainAuthError(f"Authentication failed: status={response.status_code} detail={detail}")

    def load_saved_cookies(self) -> bool:
        if not self.cookie_path.exists():
            return False
        payload = json.loads(self.cookie_path.read_text(encoding="utf-8"))
        for name, value in payload.get("cookies", {}).items():
            self.session.cookies.set(name, value)
        return True

    def _save_cookies(self, response: requests.Response | None = None) -> None:
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        if response is not None and response.headers.get("Set-Cookie"):
            cookie = SimpleCookie()
            cookie.load(response.headers["Set-Cookie"])
            for name, morsel in cookie.items():
                self.session.cookies.set(name, morsel.value)
        payload = {"cookies": requests.utils.dict_from_cookiejar(self.session.cookies)}
        self.cookie_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
