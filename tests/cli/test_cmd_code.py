"""Tests for the managed ``cmd-code`` launcher."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from free_claude_code.config.settings import Settings


def _settings(*, port: int = 9191, token: str = "proxy-token") -> Settings:
    return Settings.model_construct(
        host="0.0.0.0",
        port=port,
        anthropic_auth_token=token,
        model="nvidia_nim/test-model",
        open_admin_browser=False,
    )


def _launcher_patches(
    *, settings: Settings, session: MagicMock | None = None
) -> tuple[ExitStack, MagicMock, MagicMock, MagicMock]:
    from free_claude_code.cli.launchers import cmd_code

    session = session or MagicMock()
    acquire = MagicMock(return_value=session)
    run_client = MagicMock(side_effect=SystemExit(0))
    patches = (
        patch.object(cmd_code, "get_settings", return_value=settings),
        patch.object(
            cmd_code,
            "local_proxy_root_url",
            return_value=f"http://127.0.0.1:{settings.port}",
        ),
        patch.object(cmd_code, "acquire_server_session", acquire),
        patch.object(cmd_code, "resolve_client_binary", return_value="resolved-cmd"),
        patch.object(cmd_code, "clear_terminal"),
        patch.object(cmd_code, "cleanup_on_signal", return_value=MagicMock()),
        patch.object(cmd_code, "run_client_process", run_client),
    )
    stack = ExitStack()
    for patcher in patches:
        stack.enter_context(patcher)
    return stack, acquire, session, run_client


def test_cmd_code_launches_managed_session_and_passes_args_and_env() -> None:
    from free_claude_code.cli.launchers import cmd_code

    stack, acquire, session, run_client = _launcher_patches(settings=_settings())
    with (
        stack,
        patch.dict(
            cmd_code.os.environ,
            {
                "ANTHROPIC_API_KEY": "inherited-api-key",
                "ANTHROPIC_AUTH_TOKEN": "inherited-auth-token",
                "ANTHROPIC_BASE_URL": "https://example.invalid",
                "NO_PROXY": "existing.local",
            },
            clear=True,
        ),
        pytest.raises(SystemExit, match="0"),
    ):
        cmd_code.launch(["--print", "hello", "--model", "model-id"])

    acquire.assert_called_once()
    session.release.assert_called_once_with()
    run_client.assert_called_once()
    assert run_client.call_args.kwargs["command"] == [
        "resolved-cmd",
        "--print",
        "hello",
        "--model",
        "model-id",
    ]
    child_env = run_client.call_args.kwargs["env"]
    assert child_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9191"
    assert child_env["ANTHROPIC_AUTH_TOKEN"] == "proxy-token"
    assert child_env["ANTHROPIC_API_KEY"] == "proxy-token"
    assert child_env["NO_PROXY"] == "existing.local,127.0.0.1,localhost,::1"
    assert "ANTHROPIC_INHERITED" not in child_env


def test_cmd_code_passthrough_does_not_start_server() -> None:
    from free_claude_code.cli.launchers import cmd_code

    session = MagicMock()
    acquire = MagicMock()
    process = MagicMock()
    process.side_effect = SystemExit(0)
    with (
        patch.object(cmd_code, "resolve_client_binary", return_value="resolved-cmd"),
        patch.object(cmd_code, "acquire_server_session", acquire),
        patch.object(cmd_code, "run_client_process", process),
        pytest.raises(SystemExit, match="0"),
    ):
        cmd_code.launch(["status"])

    process.assert_called_once_with(
        command=["resolved-cmd", "status"],
        env=cmd_code.os.environ,
        binary_name="cmd",
        display_name="Command Code",
        install_hint="Install Command Code CLI, then rerun cmd-code.",
    )
    acquire.assert_not_called()
    session.release.assert_not_called()


@pytest.mark.parametrize("argv", [["--help"], ["--version"], ["feedback", "title"]])
def test_cmd_code_passthrough_flags_and_commands(argv: list[str]) -> None:
    from free_claude_code.cli.launchers import cmd_code

    with (
        patch.object(cmd_code, "resolve_client_binary", return_value="resolved-cmd"),
        patch.object(cmd_code, "run_client_process", side_effect=SystemExit(0)) as run,
        patch.object(cmd_code, "acquire_server_session") as acquire,
        pytest.raises(SystemExit, match="0"),
    ):
        cmd_code.launch(argv)

    assert run.call_args.kwargs["command"] == ["resolved-cmd", *argv]
    acquire.assert_not_called()


def test_cmd_code_releases_session_when_child_exits() -> None:
    from free_claude_code.cli.launchers import cmd_code

    session = MagicMock()
    stack, _acquire, session, _run_client = _launcher_patches(
        settings=_settings(), session=session
    )
    with (
        stack,
        patch.object(cmd_code, "run_client_process", side_effect=SystemExit(7)),
        pytest.raises(SystemExit, match="7"),
    ):
        cmd_code.launch([])

    session.release.assert_called_once_with()


def test_cmd_code_reports_server_acquisition_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from free_claude_code.cli.launchers import cmd_code
    from free_claude_code.cli.launchers.server_session import ServerSessionError

    with (
        patch.object(cmd_code, "resolve_client_binary", return_value="resolved-cmd"),
        patch.object(
            cmd_code,
            "acquire_server_session",
            side_effect=ServerSessionError("port occupied"),
        ),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_code.launch([])

    assert "Could not prepare Free Claude Code server" in capsys.readouterr().err
