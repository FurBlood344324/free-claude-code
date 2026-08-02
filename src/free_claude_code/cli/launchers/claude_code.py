"""Managed ``claude-code`` launcher."""

import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from types import FrameType

from free_claude_code.cli.launchers.claude import launch as launch_claude
from free_claude_code.cli.launchers.server_session import (
    ServerSession,
    ServerSessionError,
    acquire_server_session,
)
from free_claude_code.cli.process_registry import kill_all_best_effort
from free_claude_code.config.server_urls import local_proxy_root_url
from free_claude_code.config.settings import get_settings


def launch(argv: Sequence[str] | None = None) -> None:
    """Start a shared FCC server and launch Claude Code through it."""

    settings = get_settings()
    proxy_root_url = local_proxy_root_url(settings)
    try:
        session = acquire_server_session(
            proxy_root_url=proxy_root_url,
            port=settings.port,
        )
    except ServerSessionError as exc:
        print(f"Could not prepare Free Claude Code server: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        with _cleanup_on_signal(session):
            _clear_terminal()
            launch_claude(argv)
    finally:
        session.release()


@contextmanager
def _cleanup_on_signal(session: ServerSession) -> Iterator[None]:
    """Release a server session when the wrapper receives a termination signal."""

    previous_handlers: dict[
        int, Callable[[int, FrameType | None], object] | int | None
    ] = {}

    def handle_signal(signum: int, _frame: FrameType | None) -> None:
        kill_all_best_effort()
        session.release()
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, handle_signal)
    try:
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _clear_terminal() -> None:
    """Clear an interactive terminal without making it a launch prerequisite."""

    if not sys.stdout.isatty():
        return
    try:
        subprocess.run(
            ["clear"],
            check=False,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return
