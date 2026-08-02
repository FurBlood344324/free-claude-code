"""Tests for the managed ``pi-code`` launcher."""

from collections.abc import Sequence
from contextlib import AbstractContextManager, ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from free_claude_code.config.settings import Settings


def _launcher_settings(*, port: int = 8082, token: str = "freecc") -> Settings:
    return Settings.model_construct(
        host="0.0.0.0",
        port=port,
        anthropic_auth_token=token,
        model="nvidia_nim/test-model",
        open_admin_browser=False,
    )


def _patches(
    *,
    settings: Settings,
    extension: Path | None = None,
    session: MagicMock | None = None,
) -> tuple[
    tuple[AbstractContextManager[object], ...],
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    """Return (patches, popen, acquire, require, session) for launcher tests."""

    from free_claude_code.cli.launchers import pi_code

    if extension is None:
        extension = MagicMock()
    if session is None:
        session = MagicMock()
    popen_mock = MagicMock()
    acquire_mock = MagicMock(return_value=session)
    require_mock = MagicMock(return_value=extension)
    patches: tuple[AbstractContextManager[object], ...] = (
        patch.object(pi_code, "get_settings", return_value=settings),
        patch.object(
            pi_code,
            "local_proxy_root_url",
            return_value=f"http://127.0.0.1:{settings.port}",
        ),
        patch.object(pi_code, "require_pi_extension", require_mock),
        patch.object(pi_code, "acquire_server_session", acquire_mock),
        patch.object(pi_code, "clear_terminal"),
        patch.object(pi_code, "cleanup_on_signal", return_value=MagicMock()),
        patch("free_claude_code.cli.launchers.common.register_pid"),
        patch("free_claude_code.cli.launchers.common.unregister_pid"),
        patch(
            "free_claude_code.cli.launchers.common.subprocess.Popen",
            new=popen_mock,
        ),
    )
    return patches, popen_mock, acquire_mock, require_mock, session


def _run_launch(
    launch,
    *,
    argv: Sequence[str],
    patches: Sequence[AbstractContextManager[object]],
    extra: Sequence[AbstractContextManager[object]] = (),
    popen: MagicMock | None = None,
) -> SystemExit | None:
    """Run a pi_code launcher call under all patches.

    Returns the raised ``SystemExit`` when the launcher exits, or ``None``
    when it returns normally (e.g. after a passthrough command).
    """

    if popen is not None:
        popen.return_value.pid = 12345
        popen.return_value.wait.return_value = 0
    with ExitStack() as stack:
        for patcher in (*patches, *extra):
            stack.enter_context(patcher)
        try:
            launch(argv)
        except SystemExit as exc:
            return exc
    return None


def test_pi_code_launcher_acquires_session_and_releases(
    tmp_path: Path,
) -> None:
    from free_claude_code.cli.launchers import pi_code
    from free_claude_code.cli.launchers.pi_code import launch

    extension = tmp_path / "pi_extension.ts"
    extension.write_text("export default () => {};", encoding="utf-8")
    settings = _launcher_settings(port=9191, token="proxy-token")
    patches, popen, _acquire, _require, session = _patches(
        settings=settings, extension=extension
    )

    exit_code = _run_launch(
        launch,
        argv=["--print", "hello"],
        patches=patches,
        popen=popen,
        extra=(patch.object(pi_code, "prepare_pi_launch", return_value="resolved-pi"),),
    )

    assert exit_code is not None
    assert exit_code.code == 0
    assert popen.call_args.args[0] == [
        "resolved-pi",
        "-e",
        str(extension),
        "--models",
        "free-claude-code/**",
        "--print",
        "hello",
    ]
    child_env = popen.call_args.kwargs["env"]
    assert child_env["FCC_PI_BASE_URL"] == "http://127.0.0.1:9191"
    assert child_env["FCC_PI_API_KEY"] == "proxy-token"
    assert child_env["NO_PROXY"] == "127.0.0.1,localhost,::1"
    session.release.assert_called_once_with()


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["--version"],
        ["config", "set", "theme", "dark"],
        ["install", "npm:example"],
        ["list"],
        ["remove", "npm:example"],
        ["uninstall", "npm:example"],
        ["update"],
    ],
)
def test_pi_code_passes_management_commands_through_without_server(
    argv: list[str],
) -> None:
    from free_claude_code.cli.launchers import pi_code
    from free_claude_code.cli.launchers.pi_code import launch

    settings = _launcher_settings()
    patches, popen, acquire, require, session = _patches(settings=settings)
    prepare_mock = MagicMock(return_value=None)

    exit_code = _run_launch(
        launch,
        argv=argv,
        patches=patches,
        popen=popen,
        extra=(patch.object(pi_code, "prepare_pi_launch", prepare_mock),),
    )

    assert exit_code is None
    prepare_mock.assert_called_once_with(argv)
    popen.assert_not_called()
    session.release.assert_not_called()
    acquire.assert_not_called()
    require.assert_not_called()


def test_pi_code_fails_closed_when_server_cannot_be_acquired(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from free_claude_code.cli.launchers import pi_code
    from free_claude_code.cli.launchers.pi_code import launch
    from free_claude_code.cli.launchers.server_session import ServerSessionError

    extension = tmp_path / "pi_extension.ts"
    extension.write_text("export default () => {};", encoding="utf-8")
    settings = _launcher_settings()
    patches, popen, _acquire, _require, session = _patches(
        settings=settings, extension=extension
    )

    exit_code = _run_launch(
        launch,
        argv=[],
        patches=patches,
        extra=(
            patch.object(pi_code, "prepare_pi_launch", return_value="resolved-pi"),
            patch.object(
                pi_code,
                "acquire_server_session",
                side_effect=ServerSessionError("port occupied"),
            ),
        ),
    )

    assert exit_code is not None
    assert exit_code.code == 1
    popen.assert_not_called()
    session.release.assert_not_called()
    assert "Could not prepare Free Claude Code server" in capsys.readouterr().err


def test_pi_code_fails_closed_when_bundled_extension_is_missing() -> None:
    from free_claude_code.cli.launchers import pi_code
    from free_claude_code.cli.launchers.pi_code import launch

    settings = _launcher_settings()
    patches, popen, _acquire, _require, session = _patches(settings=settings)

    exit_code = _run_launch(
        launch,
        argv=[],
        patches=patches,
        extra=(
            patch.object(pi_code, "prepare_pi_launch", return_value="resolved-pi"),
            patch.object(pi_code, "require_pi_extension", side_effect=SystemExit(1)),
        ),
    )

    assert exit_code is not None
    assert exit_code.code == 1
    popen.assert_not_called()
    session.release.assert_not_called()


def test_pi_code_rejects_unrelated_pi_binary() -> None:
    from free_claude_code.cli.launchers import pi_code
    from free_claude_code.cli.launchers.pi_code import launch

    settings = _launcher_settings()
    patches, popen, _acquire, _require, session = _patches(settings=settings)

    exit_code = _run_launch(
        launch,
        argv=[],
        patches=patches,
        extra=(
            patch.object(pi_code, "prepare_pi_launch", side_effect=SystemExit(126)),
        ),
    )

    assert exit_code is not None
    assert exit_code.code == 126
    popen.assert_not_called()
    session.release.assert_not_called()
