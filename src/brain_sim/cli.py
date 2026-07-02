from __future__ import annotations

import argparse
import getpass
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from . import __version__
from .auth import BrainAuth, load_credentials
from .batch import BatchRunner, BatchSize
from .client import BrainClient
from .excel import read_excel_expressions
from .models import AuthChallenge
from .notify import SmtpNotifier
from .payloads import build_payload_record


DEFAULT_CREDENTIALS_FILE = "~/.brain_credentials"
DEFAULT_COOKIE_PATH = ".brain_sim/cookies.json"
LOGIN_LINK_PATH = Path(".brain_sim/latest_login_link.json")


def _prompt_credentials() -> tuple[str, str]:
    email = input("WorldQuant BRAIN email: ")
    password = getpass.getpass("WorldQuant BRAIN password: ")
    return email, password


def _write_login_link(challenge: AuthChallenge) -> None:
    LOGIN_LINK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOGIN_LINK_PATH.write_text(
        json.dumps(
            {
                "url": challenge.url,
                "www_authenticate": challenge.www_authenticate,
                "message": challenge.message,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _timestamp_run_dir() -> Path:
    return Path("runs") / f"brain-sim-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def _batch_size(value: str) -> BatchSize:
    if value == "auto":
        return "auto"
    return int(value)  # type: ignore[return-value]


def _command_login(args: argparse.Namespace) -> int:
    if args.prompt:
        email, password = _prompt_credentials()
    else:
        try:
            email, password = load_credentials(str(_expanded_path(args.credentials_file)))
        except Exception as exc:  # noqa: BLE001 - convert config failures into CLI-grade errors.
            raise SystemExit(f"Could not load BRAIN credentials from {args.credentials_file}: {exc}") from exc

    notifier = SmtpNotifier() if args.notify_email else None
    cookie_path = _expanded_path(args.cookie_path)
    auth = BrainAuth(cookie_path=cookie_path, notifier=notifier)
    try:
        result = auth.login(email, password, notify_email=args.notify_email)
    except Exception as exc:  # noqa: BLE001 - present auth failures without a traceback.
        raise SystemExit(f"BRAIN login failed: {exc}") from exc

    if isinstance(result, AuthChallenge):
        _write_login_link(result)
        if args.print_link or not args.notify_email:
            print(result.url)
        if result.message:
            print(result.message)
        print(f"Login verification required. Link saved to {LOGIN_LINK_PATH}.")
        return 2

    print(f"Login succeeded. Cookies saved to {cookie_path}.")
    return 0


def _command_simulate_excel(args: argparse.Namespace) -> int:
    session = requests.Session()
    cookie_path = _expanded_path(args.cookie_path)
    auth = BrainAuth(session=session, cookie_path=cookie_path)
    if not auth.load_saved_cookies():
        raise SystemExit(
            f"No saved BRAIN cookies found at {cookie_path}. "
            "Run `brain-sim login` first."
        )

    run_dir = _expanded_path(args.run_dir) if args.run_dir else _timestamp_run_dir()
    excel_path = _expanded_path(args.excel_path)
    expressions = read_excel_expressions(excel_path, sheet_name=args.sheet or None)
    records = [build_payload_record(expression) for expression in expressions]
    client = BrainClient(session=session)
    runner = BatchRunner(client, run_dir)
    summary = runner.run(
        records,
        batch_size=_batch_size(args.batch_size),
        poll_timeout_seconds=args.poll_timeout_seconds,
        recordsets=args.recordset,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("failed", 0) == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain-sim")
    parser.add_argument("--version", action="version", version=f"brain-sim {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    login = subparsers.add_parser("login", help="Authenticate with WorldQuant BRAIN.")
    login.add_argument("--credentials-file", default=DEFAULT_CREDENTIALS_FILE)
    login.add_argument("--cookie-path", default=DEFAULT_COOKIE_PATH)
    login.add_argument("--notify-email", default="")
    login.add_argument("--print-link", action="store_true")
    login.add_argument("--prompt", action="store_true")
    login.set_defaults(func=_command_login)

    simulate = subparsers.add_parser("simulate-excel", help="Run BRAIN simulations from an Excel file.")
    simulate.add_argument("excel_path")
    simulate.add_argument("--sheet", default="")
    simulate.add_argument("--run-dir", default="")
    simulate.add_argument("--cookie-path", default=DEFAULT_COOKIE_PATH)
    simulate.add_argument("--batch-size", choices=("auto", "8", "4", "1"), default="auto")
    simulate.add_argument("--poll-timeout-seconds", type=float, default=900)
    simulate.add_argument("--recordset", action="append", default=[])
    simulate.set_defaults(func=_command_simulate_excel)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Any | None = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    return int(func(args))
