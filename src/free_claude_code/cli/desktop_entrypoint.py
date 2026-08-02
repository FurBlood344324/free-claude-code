"""Lightweight entrypoint for the optional FCC desktop shell."""

import sys
from collections.abc import Sequence
from pathlib import Path

from free_claude_code.cli.desktop_assets import export_app_icon

_SUPPORTED_PLATFORMS = {"darwin", "win32", "linux"}


def _report_tray_unavailable(exc: Exception) -> None:
    """Explain why the native tray could not start and how to fix it."""

    if sys.platform == "linux":
        print(
            "FCC Desktop needs a graphical system tray on Linux; install "
            "AppIndicator/GTK Python bindings (python3-gi plus "
            "gir1.2-appindicator3-0.1 or gir1.2-gtk-3.0) or run inside an "
            "X11 session.",
            file=sys.stderr,
        )
    else:
        print("FCC Desktop dependencies are unavailable.", file=sys.stderr)
    print(str(exc), file=sys.stderr)


def launch(argv: Sequence[str] | None = None) -> None:
    """Export installer assets or launch the supported native tray adapter."""

    args = tuple(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--export-icon":
        export_app_icon(Path(args[1]))
        return
    if args:
        print("Usage: fcc-desktop [--export-icon PATH]", file=sys.stderr)
        raise SystemExit(2)
    if sys.platform not in _SUPPORTED_PLATFORMS:
        print(
            "FCC Desktop is supported on Windows, macOS, and Linux.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        from free_claude_code.cli.desktop_tray import launch as launch_tray
    except Exception as exc:
        _report_tray_unavailable(exc)
        raise SystemExit(1) from exc

    launch_tray()
