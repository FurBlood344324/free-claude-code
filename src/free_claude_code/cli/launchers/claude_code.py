"""Managed ``claude-code`` launcher."""

import sys
from collections.abc import Sequence

from free_claude_code.cli.launchers.claude import launch as launch_claude
from free_claude_code.cli.launchers.common import clear_terminal
from free_claude_code.cli.launchers.server_session import (
    ServerSessionError,
    acquire_server_session,
    cleanup_on_signal,
)
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
        with cleanup_on_signal(session):
            clear_terminal()
            launch_claude(argv)
    finally:
        session.release()
