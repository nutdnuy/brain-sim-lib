from __future__ import annotations

import json
from pathlib import Path
import runpy

import pytest

from brain_sim import cli
from brain_sim.models import AuthChallenge


def test_parser_exposes_login_and_simulate_excel() -> None:
    parser = cli.build_parser()
    subcommands_action = next(
        action for action in parser._actions if getattr(action, "dest", None) == "command"
    )

    assert {"login", "simulate-excel"}.issubset(subcommands_action.choices)


def test_parser_parses_login_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "login",
            "--credentials-file",
            "creds.json",
            "--cookie-path",
            "cookies.json",
            "--notify-email",
            "me@example.com",
            "--print-link",
            "--prompt",
        ]
    )

    assert args.command == "login"
    assert args.credentials_file == "creds.json"
    assert args.cookie_path == "cookies.json"
    assert args.notify_email == "me@example.com"
    assert args.print_link is True
    assert args.prompt is True


def test_parser_parses_simulate_excel_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "simulate-excel",
            "alphas.xlsx",
            "--sheet",
            "Sheet2",
            "--run-dir",
            "run-1",
            "--cookie-path",
            "cookies.json",
            "--batch-size",
            "4",
            "--poll-timeout-seconds",
            "12.5",
            "--recordset",
            "self_correlation",
            "--recordset",
            "pnl",
        ]
    )

    assert args.command == "simulate-excel"
    assert args.excel_path == "alphas.xlsx"
    assert args.sheet == "Sheet2"
    assert args.run_dir == "run-1"
    assert args.cookie_path == "cookies.json"
    assert args.batch_size == "4"
    assert args.poll_timeout_seconds == 12.5
    assert args.recordset == ["self_correlation", "pnl"]


def test_main_help_and_version(capsys) -> None:
    with pytest.raises(SystemExit) as help_exit:
        cli.main(["--help"])
    assert help_exit.value.code == 0
    assert "simulate-excel" in capsys.readouterr().out

    with pytest.raises(SystemExit) as version_exit:
        cli.main(["--version"])
    assert version_exit.value.code == 0
    assert "brain-sim" in capsys.readouterr().out


def test_login_challenge_prints_and_stores_link(monkeypatch, tmp_path, capsys) -> None:
    created: dict[str, object] = {}

    class FakeNotifier:
        pass

    class FakeAuth:
        def __init__(self, *, cookie_path, notifier=None):
            created["cookie_path"] = cookie_path
            created["notifier"] = notifier

        def login(self, email, password, *, notify_email=None):
            created["login"] = (email, password, notify_email)
            return AuthChallenge(
                url="https://verify.example/inquiry",
                www_authenticate="persona",
                message="verify",
            )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "SmtpNotifier", FakeNotifier)
    monkeypatch.setattr(cli, "load_credentials", lambda path: ("u@example.com", "secret"))

    result = cli.main(
        [
            "login",
            "--credentials-file",
            "creds.json",
            "--cookie-path",
            "cookies.json",
            "--notify-email",
            "me@example.com",
            "--print-link",
        ]
    )

    assert result == 2
    assert created["cookie_path"] == Path("cookies.json")
    assert isinstance(created["notifier"], FakeNotifier)
    assert created["login"] == ("u@example.com", "secret", "me@example.com")
    assert "https://verify.example/inquiry" in capsys.readouterr().out
    saved = json.loads((tmp_path / ".brain_sim/latest_login_link.json").read_text())
    assert saved["url"] == "https://verify.example/inquiry"
    assert saved["www_authenticate"] == "persona"


def test_login_challenge_prints_link_without_notify_email(monkeypatch, tmp_path, capsys) -> None:
    class FakeAuth:
        def __init__(self, *, cookie_path, notifier=None):
            assert notifier is None

        def login(self, email, password, *, notify_email=None):
            return AuthChallenge(
                url="https://verify.example/no-notify",
                www_authenticate="persona",
                message="verify",
            )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "load_credentials", lambda path: ("u@example.com", "secret"))

    result = cli.main(["login"])

    assert result == 2
    assert "https://verify.example/no-notify" in capsys.readouterr().out


def test_login_success_returns_zero(monkeypatch, capsys) -> None:
    class FakeAuth:
        def __init__(self, *, cookie_path, notifier=None):
            self.cookie_path = cookie_path

        def login(self, email, password, *, notify_email=None):
            return None

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "load_credentials", lambda path: ("u@example.com", "secret"))

    result = cli.main(["login", "--cookie-path", "cookies.json"])

    assert result == 0
    assert "Cookies saved to cookies.json" in capsys.readouterr().out


def test_login_credentials_error_is_cli_grade(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_credentials", lambda path: (_ for _ in ()).throw(FileNotFoundError(path)))

    with pytest.raises(SystemExit) as exc:
        cli.main(["login", "--credentials-file", "missing.json"])

    assert "Could not load BRAIN credentials from missing.json" in str(exc.value)


def test_login_prompt_uses_input_and_getpass(monkeypatch) -> None:
    seen: dict[str, tuple[str, str, str]] = {}

    class FakeAuth:
        def __init__(self, *, cookie_path, notifier=None):
            pass

        def login(self, email, password, *, notify_email=None):
            seen["login"] = (email, password, notify_email)
            return None

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr("builtins.input", lambda prompt: "prompt@example.com")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "prompt-secret")

    assert cli.main(["login", "--prompt"]) == 0
    assert seen["login"] == ("prompt@example.com", "prompt-secret", "")


def test_simulate_excel_missing_cookies_raises_helpful_system_exit(monkeypatch) -> None:
    class FakeAuth:
        def __init__(self, *, session, cookie_path):
            self.cookie_path = cookie_path

        def load_saved_cookies(self):
            return False

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)

    with pytest.raises(SystemExit) as exc:
        cli.main(["simulate-excel", "alphas.xlsx", "--cookie-path", "missing.json"])

    assert "No saved BRAIN cookies found at missing.json" in str(exc.value)
    assert "brain-sim login" in str(exc.value)


def test_simulate_excel_success_wires_dependencies_and_returns_zero(monkeypatch, tmp_path, capsys) -> None:
    calls: dict[str, object] = {}

    class FakeAuth:
        def __init__(self, *, session, cookie_path):
            calls["auth"] = (session, cookie_path)

        def load_saved_cookies(self):
            return True

    class FakeClient:
        def __init__(self, *, session):
            calls["client_session"] = session

    class FakeRunner:
        def __init__(self, client, run_dir):
            calls["runner_init"] = (client, run_dir)

        def run(self, records, *, batch_size, poll_timeout_seconds, recordsets):
            calls["run"] = (records, batch_size, poll_timeout_seconds, recordsets)
            return {"failed": 0, "completed": 2, "run_dir": "run-1"}

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "BrainClient", FakeClient)
    monkeypatch.setattr(cli, "BatchRunner", FakeRunner)
    monkeypatch.setattr(cli, "read_excel_expressions", lambda path, *, sheet_name=None: ["expr-1", "expr-2"])
    monkeypatch.setattr(cli, "build_payload_record", lambda expression: f"record-{expression}")

    result = cli.main(
        [
            "simulate-excel",
            "alphas.xlsx",
            "--sheet",
            "AlphaSheet",
            "--run-dir",
            str(tmp_path / "run-1"),
            "--batch-size",
            "4",
            "--poll-timeout-seconds",
            "10",
            "--recordset",
            "self",
        ]
    )

    assert result == 0
    assert calls["auth"][1] == (Path(cli.DEFAULT_COOKIE_PATH).expanduser())
    assert calls["runner_init"][1] == tmp_path / "run-1"
    assert calls["run"] == (["record-expr-1", "record-expr-2"], 4, 10.0, ["self"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["failed"] == 0


def test_simulate_excel_expands_cookie_and_run_paths(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}
    cookie_path = tmp_path / "cookies.json"
    run_path = tmp_path / "run"

    class FakeAuth:
        def __init__(self, *, session, cookie_path):
            calls["cookie_path"] = cookie_path

        def load_saved_cookies(self):
            return True

    class FakeClient:
        def __init__(self, *, session):
            pass

    class FakeRunner:
        def __init__(self, client, run_dir):
            calls["run_dir"] = run_dir

        def run(self, records, *, batch_size, poll_timeout_seconds, recordsets):
            return {"failed": 0}

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "BrainClient", FakeClient)
    monkeypatch.setattr(cli, "BatchRunner", FakeRunner)
    monkeypatch.setattr(cli, "read_excel_expressions", lambda path, *, sheet_name=None: ["expr"])
    monkeypatch.setattr(cli, "build_payload_record", lambda expression: expression)

    assert cli.main(
        [
            "simulate-excel",
            "alphas.xlsx",
            "--cookie-path",
            str(cookie_path),
            "--run-dir",
            str(run_path),
        ]
    ) == 0
    assert calls["cookie_path"] == cookie_path
    assert calls["run_dir"] == run_path


def test_simulate_excel_failed_summary_returns_one(monkeypatch, tmp_path) -> None:
    class FakeAuth:
        def __init__(self, *, session, cookie_path):
            pass

        def load_saved_cookies(self):
            return True

    class FakeClient:
        def __init__(self, *, session):
            pass

    class FakeRunner:
        def __init__(self, client, run_dir):
            pass

        def run(self, records, *, batch_size, poll_timeout_seconds, recordsets):
            return {"failed": 1, "completed": 0, "run_dir": str(tmp_path)}

    monkeypatch.setattr(cli, "BrainAuth", FakeAuth)
    monkeypatch.setattr(cli, "BrainClient", FakeClient)
    monkeypatch.setattr(cli, "BatchRunner", FakeRunner)
    monkeypatch.setattr(cli, "read_excel_expressions", lambda path, *, sheet_name=None: ["expr"])
    monkeypatch.setattr(cli, "build_payload_record", lambda expression: f"record-{expression}")

    assert cli.main(["simulate-excel", "alphas.xlsx", "--run-dir", str(tmp_path)]) == 1


def test_module_execution_propagates_main_return_code(monkeypatch) -> None:
    monkeypatch.setattr(cli, "main", lambda: 7)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("brain_sim", run_name="__main__")

    assert exc.value.code == 7
