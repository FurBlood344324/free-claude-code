from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from free_claude_code.cli.launchers.server_session import (
    ServerSessionError,
    ServerSessionPaths,
    acquire_server_session,
)


def _paths(tmp_path: Path) -> ServerSessionPaths:
    return ServerSessionPaths(
        lock=tmp_path / "server.lock",
        references=tmp_path / "server.refs",
        pid=tmp_path / "server.pid",
    )


def test_acquire_reuses_healthy_server(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.pid.write_text("123\n", encoding="utf-8")
    paths.references.write_text("900\n", encoding="utf-8")

    with (
        patch(
            "free_claude_code.cli.launchers.server_session._process_is_alive",
            return_value=True,
        ),
        patch(
            "free_claude_code.cli.launchers.server_session._is_fcc_server_process",
            return_value=True,
        ),
    ):
        session = acquire_server_session(
            proxy_root_url="http://127.0.0.1:8082",
            port=8082,
            paths=paths,
            pid=901,
            wait_for_ready=lambda _url: None,
        )

    assert session.server_pid == 123
    assert paths.references.read_text(encoding="utf-8").splitlines() == ["900", "901"]
    session.release()


def test_acquire_starts_server_and_waits_for_health(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    process = MagicMock()
    process.pid = 321
    process.poll.return_value = None
    readiness = iter(["not ready", None])

    start = MagicMock(return_value=process)
    with patch(
        "free_claude_code.cli.launchers.server_session._port_is_open",
        return_value=False,
    ):
        session = acquire_server_session(
            proxy_root_url="http://127.0.0.1:8082",
            port=8082,
            paths=paths,
            pid=901,
            process_factory=start,
            wait_for_ready=lambda _url: next(readiness),
            sleep=lambda _seconds: None,
            monotonic=iter([0.0, 0.1, 11.0]).__next__,
        )

    start.assert_called_once()
    assert session.server_pid == 321
    session.release()
    process.wait.assert_not_called()


def test_acquire_refuses_occupied_non_fcc_port(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    with (
        patch(
            "free_claude_code.cli.launchers.server_session._port_is_open",
            return_value=True,
        ),
        pytest.raises(ServerSessionError, match="occupied by another process"),
    ):
        acquire_server_session(
            proxy_root_url="http://127.0.0.1:8082",
            port=8082,
            paths=paths,
            wait_for_ready=lambda _url: "not ready",
        )


def test_last_reference_stops_owned_server(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.pid.write_text("321\n", encoding="utf-8")
    session = acquire_server_session(
        proxy_root_url="http://127.0.0.1:8082",
        port=8082,
        paths=paths,
        pid=901,
        wait_for_ready=lambda _url: None,
    )
    session.owns_server = True

    with (
        patch("free_claude_code.cli.launchers.server_session._stop_process") as stop,
        patch(
            "free_claude_code.cli.launchers.server_session._is_fcc_server_process",
            return_value=True,
        ),
    ):
        session.release()
        session.release()

    stop.assert_called_once_with(321)
    assert not paths.references.exists()
    assert not paths.pid.exists()


def test_non_last_reference_keeps_owned_server(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.pid.write_text("321\n", encoding="utf-8")
    first = acquire_server_session(
        proxy_root_url="http://127.0.0.1:8082",
        port=8082,
        paths=paths,
        pid=901,
        wait_for_ready=lambda _url: None,
    )
    second = acquire_server_session(
        proxy_root_url="http://127.0.0.1:8082",
        port=8082,
        paths=paths,
        pid=902,
        wait_for_ready=lambda _url: None,
    )
    first.owns_server = True
    second.owns_server = True

    with (
        patch("free_claude_code.cli.launchers.server_session._stop_process") as stop,
        patch(
            "free_claude_code.cli.launchers.server_session._process_is_alive",
            return_value=True,
        ),
    ):
        first.release()
        stop.assert_not_called()
        second.release()

    stop.assert_called_once_with(321)


def test_claude_code_launcher_delegates_and_releases() -> None:
    from free_claude_code.cli.launchers import claude_code

    session = MagicMock()
    settings = MagicMock(port=8082)
    settings.host = "127.0.0.1"
    settings.anthropic_auth_token = "token"

    with (
        patch.object(claude_code, "get_settings", return_value=settings),
        patch.object(
            claude_code, "local_proxy_root_url", return_value="http://127.0.0.1:8082"
        ),
        patch.object(claude_code, "acquire_server_session", return_value=session),
        patch.object(claude_code, "clear_terminal"),
        patch.object(claude_code, "launch_claude", side_effect=SystemExit(7)) as launch,
        pytest.raises(SystemExit, match="7"),
    ):
        claude_code.launch(["--resume", "session"])

    launch.assert_called_once_with(["--resume", "session"])
    session.release.assert_called_once_with()


def test_signal_cleanup_stops_child_and_releases_session() -> None:
    from free_claude_code.cli.launchers import server_session

    session = MagicMock()
    with (
        patch.object(server_session, "kill_all_best_effort") as kill_children,
        patch.object(server_session.signal, "getsignal", return_value=None),
        patch.object(server_session.signal, "signal") as install_signal,
        server_session.cleanup_on_signal(session),
    ):
        handler = install_signal.call_args_list[0].args[1]
        with pytest.raises(SystemExit, match="130"):
            handler(server_session.signal.SIGINT, None)

    kill_children.assert_called_once_with()
    session.release.assert_called_once_with()
    assert install_signal.call_count == 4


def test_signal_cleanup_is_idempotent_with_outer_release() -> None:
    from free_claude_code.cli.launchers import server_session

    session = MagicMock()
    with (
        patch.object(server_session, "kill_all_best_effort"),
        patch.object(server_session.signal, "getsignal", return_value=None),
        patch.object(server_session.signal, "signal") as install_signal,
        server_session.cleanup_on_signal(session),
    ):
        handler = install_signal.call_args_list[0].args[1]
        with pytest.raises(SystemExit):
            handler(server_session.signal.SIGTERM, None)

    session.release.assert_called_once_with()
