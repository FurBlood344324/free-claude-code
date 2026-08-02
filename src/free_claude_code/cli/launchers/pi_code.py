"""Managed ``pi-code`` launcher: Pi through a shared FCC server."""

import os
import sys
from collections.abc import Sequence

from free_claude_code.cli.launchers.common import clear_terminal, run_client_process
from free_claude_code.cli.launchers.pi import (
    build_pi_launcher_command,
    build_pi_launcher_env,
    pi_install_hint,
    prepare_pi_launch,
    require_pi_extension,
)
from free_claude_code.cli.launchers.server_session import (
    ServerSessionError,
    acquire_server_session,
    cleanup_on_signal,
)
from free_claude_code.config.server_urls import local_proxy_root_url
from free_claude_code.config.settings import get_settings

_BINARY_NAME = "pi"
_DISPLAY_NAME = "Pi"


def launch(argv: Sequence[str] | None = None) -> None:
    """Start a shared FCC server and launch Pi through it."""

    args = list(sys.argv[1:] if argv is None else argv)
    binary_path = prepare_pi_launch(args)
    if binary_path is None:
        return
    extension_path = require_pi_extension()

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
            run_client_process(
                command=build_pi_launcher_command(
                    binary_path=binary_path,
                    extension_path=extension_path,
                    argv=args,
                ),
                env=build_pi_launcher_env(
                    proxy_root_url=proxy_root_url,
                    auth_token=settings.anthropic_auth_token,
                    base_env=os.environ,
                ),
                binary_name=_BINARY_NAME,
                display_name=_DISPLAY_NAME,
                install_hint=pi_install_hint(),
            )
    finally:
        session.release()
