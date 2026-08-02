"""Tray adapters for the Windows tray, macOS menu bar, and Linux status area."""

import sys
from io import BytesIO

from PIL import Image
from pystray import Icon, Menu, MenuItem

from free_claude_code.cli.desktop import (
    DesktopController,
    HeadlessDesktopTray,
    launch_desktop,
)
from free_claude_code.cli.desktop_assets import app_icon_bytes

_X11_SYSTRAY_SELECTION = "_NET_SYSTEM_TRAY_S0"


class PystrayDesktopTray:
    """Render desktop lifecycle actions through the native status area."""

    def __init__(self, controller: DesktopController) -> None:
        self._controller = controller
        self._icon = Icon(
            "free-claude-code",
            _create_icon(),
            "Free Claude Code",
            Menu(
                MenuItem("Open", self._open_admin, default=True),
                MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        self._icon.run()

    def stop(self) -> None:
        self._icon.stop()

    def _open_admin(self, _icon: Icon, _item: MenuItem) -> None:
        self._controller.open_admin()

    def _quit(self, _icon: Icon, _item: MenuItem) -> None:
        self._controller.quit()


def _x11_systray_available() -> bool:
    """Return True when an X11 systray manager owns the systray selection."""

    try:
        from Xlib import X
        from Xlib.display import Display
    except ImportError:
        return False
    try:
        connection = Display()
    except Exception:
        return False
    try:
        owner = connection.get_selection_owner(
            connection.intern_atom(_X11_SYSTRAY_SELECTION)
        )
        return owner != X.NONE
    finally:
        connection.close()


def _systray_available() -> bool:
    """Return True when the active pystray backend can host the tray icon."""

    if sys.platform != "linux":
        return True
    backend_name = Icon.__module__.rsplit(".", 1)[-1]
    if backend_name != "_xorg":
        # GI-based backends register a StatusNotifierItem over DBus.
        return True
    return _x11_systray_available()


def _sni_host_available() -> bool:
    """Return True when a StatusNotifierItem host can display the tray."""

    if sys.platform != "linux":
        return False
    # dbus-fast is only installed on Linux, so keep the SNI import lazy.
    from free_claude_code.cli.sni_tray import sni_host_available

    return sni_host_available()


def _create_icon() -> Image.Image:
    """Load the same branded artwork used by native desktop launchers."""

    with Image.open(BytesIO(app_icon_bytes(".png"))) as image:
        return image.convert("RGBA")


def launch() -> None:
    """Launch the native tray adapter or degrade to headless mode."""

    if _sni_host_available():
        # dbus-fast is only installed on Linux, so keep the SNI import lazy.
        from free_claude_code.cli.sni_tray import StatusNotifierDesktopTray

        launch_desktop(StatusNotifierDesktopTray)
        return
    if not _systray_available():
        print(
            "FCC Desktop could not find a system tray on this desktop; it is "
            "running in background mode without a tray icon. The Admin UI "
            "will open in your browser. Stop FCC Desktop with: pkill fcc-desktop",
            file=sys.stderr,
        )
        launch_desktop(HeadlessDesktopTray)
        return
    launch_desktop(PystrayDesktopTray)
