"""Managed ``cmd-code`` launcher: Command Code through a shared FCC server."""

import os
import sys
from collections.abc import Mapping, Sequence

from free_claude_code.cli.local_http import with_local_proxy_bypass
from free_claude_code.cli.proxy_auth import proxy_auth_token
from free_claude_code.config.server_urls import local_proxy_root_url
from free_claude_code.config.settings import get_settings

from .common import (
    clear_terminal,
    resolve_client_binary,
    run_client_process,
)
from .server_session import (
    ServerSessionError,
    acquire_server_session,
    cleanup_on_signal,
)

_BINARY_NAME = "cmd"
_DISPLAY_NAME = "Command Code"
_INSTALL_HINT = "Install Command Code CLI, then rerun cmd-code."
_PASSTHROUGH_COMMANDS = frozenset(
    {
        "feedback",
        "help",
        "info",
        "learn-taste",
        "login",
        "logout",
        "mcp",
        "mods",
        "skills",
        "status",
        "taste",
        "update",
        "whoami",
    }
)
_PASSTHROUGH_FLAGS = frozenset({"--help", "-h", "--version", "-v"})
_STRIPPED_ANTHROPIC_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
    }
)


def launch(argv: Sequence[str] | None = None) -> None:
    """Start a shared FCC server and launch Command Code through it."""

    args = list(sys.argv[1:] if argv is None else argv)
    binary_path = resolve_client_binary(
        binary_name=_BINARY_NAME,
        display_name=_DISPLAY_NAME,
        install_hint=_INSTALL_HINT,
    )
    if is_cmd_passthrough(args):
        run_client_process(
            command=[binary_path, *args],
            env=os.environ,
            binary_name=_BINARY_NAME,
            display_name=_DISPLAY_NAME,
            install_hint=_INSTALL_HINT,
        )
        return

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
                command=[binary_path, *args],
                env=build_cmd_proxy_env(
                    proxy_root_url=proxy_root_url,
                    auth_token=settings.anthropic_auth_token,
                    base_env=os.environ,
                ),
                binary_name=_BINARY_NAME,
                display_name=_DISPLAY_NAME,
                install_hint=_INSTALL_HINT,
            )
    finally:
        session.release()


def build_cmd_proxy_env(
    *,
    proxy_root_url: str,
    auth_token: str,
    base_env: Mapping[str, str],
) -> dict[str, str]:
    """Return the environment for a Command Code proxy session."""

    env = with_local_proxy_bypass(
        {
            key: value
            for key, value in base_env.items()
            if key not in _STRIPPED_ANTHROPIC_ENV_KEYS
        },
        proxy_root_url=proxy_root_url,
    )
    token = proxy_auth_token(auth_token)
    env["ANTHROPIC_BASE_URL"] = proxy_root_url
    env["ANTHROPIC_AUTH_TOKEN"] = token
    env["ANTHROPIC_API_KEY"] = token
    return env


def is_cmd_passthrough(argv: Sequence[str]) -> bool:
    """Return whether Command Code can run without an FCC server session."""

    return bool(argv) and (
        argv[0] in _PASSTHROUGH_COMMANDS or argv[0] in _PASSTHROUGH_FLAGS
    )
