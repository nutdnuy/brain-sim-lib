from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .models import AuthChallenge
from .notify import Notifier


API_BASE = "https://api.worldquantbrain.com"


class BrainAuthError(RuntimeError):
    pass


def _is_persona_challenge(value: str | None) -> bool:
    if not value:
        return False
    for challenge in value.split(","):
        scheme = challenge.strip().split(None, 1)[0].split(";", 1)[0]
        if scheme.lower() == "persona":
            return True
    return False


def _cookie_to_dict(cookie: Cookie, default_domain: str = "api.worldquantbrain.com") -> dict[str, Any]:
    return {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain or default_domain,
        "path": cookie.path or "/",
        "secure": cookie.secure,
        "expires": cookie.expires,
    }


def _is_cookie_domain_for_host(domain: str | None, host: str) -> bool:
    if not domain:
        return True
    normalized_domain = domain.lstrip(".").lower()
    normalized_host = host.lower()
    host_parts = normalized_host.split(".")
    parent_domain = ".".join(host_parts[1:]) if len(host_parts) > 2 else normalized_host
    return normalized_domain in {normalized_host, parent_domain}


def _parse_cookie_expires(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except (TypeError, ValueError, OverflowError):
        return None


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
        self.cookie_domain = urlparse(self.api_base).hostname or "api.worldquantbrain.com"

    def login(self, email: str, password: str, *, notify_email: str | None = None) -> AuthChallenge | None:
        response = self.session.post(
            f"{self.api_base}/authentication",
            auth=(email, password),
            timeout=60,
        )
        if response.status_code in (200, 201):
            self._save_cookies(response)
            return None

        if response.status_code == 401 and _is_persona_challenge(response.headers.get("WWW-Authenticate")):
            location = response.headers.get("Location", "")
            url = urljoin(response.url, location)
            message = "WorldQuant BRAIN requires Persona verification."
            if notify_email and self.notifier:
                try:
                    self.notifier.send_login_link(notify_email, url)
                except Exception as exc:
                    message = f"{message} Notification failed: {exc}"
            return AuthChallenge(url=url, www_authenticate="persona", message=message)

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
        cookies = payload.get("cookies", [])
        if isinstance(cookies, dict):
            for name, value in cookies.items():
                self.session.cookies.set(
                    name,
                    value,
                    domain=self.cookie_domain,
                    path="/",
                    secure=True,
                )
            return True
        for cookie in cookies:
            if not _is_cookie_domain_for_host(cookie.get("domain"), self.cookie_domain):
                continue
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain") or self.cookie_domain,
                path=cookie.get("path") or "/",
                secure=bool(cookie.get("secure")),
                expires=cookie.get("expires"),
            )
        return True

    def _save_cookies(self, response: requests.Response | None = None) -> None:
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        if response is not None and response.headers.get("Set-Cookie"):
            cookie = SimpleCookie()
            cookie.load(response.headers["Set-Cookie"])
            for name, morsel in cookie.items():
                self.session.cookies.set(
                    name,
                    morsel.value,
                    domain=morsel["domain"] or self.cookie_domain,
                    path=morsel["path"] or "/",
                    secure=bool(morsel["secure"]),
                    expires=_parse_cookie_expires(morsel["expires"]),
                )
        cookies = [
            _cookie_to_dict(cookie, self.cookie_domain)
            for cookie in self.session.cookies
            if _is_cookie_domain_for_host(cookie.domain, self.cookie_domain)
        ]
        payload = {"cookies": cookies}
        self.cookie_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.cookie_path.chmod(0o600)
