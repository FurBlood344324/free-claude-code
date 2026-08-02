"""StatusNotifierItem tray adapter for Wayland and SNI-capable desktops.

X11 system trays are not available on Wayland compositors, so this module
serves the FCC Desktop menu through the cross-desktop StatusNotifierItem
protocol over the session DBus. Desktops like niri, sway, and KDE Plasma
display SNI items natively or through a bar widget (waybar, quickshell, ...).
"""

import asyncio
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any

from dbus_fast import BusType, Message, MessageType, NameFlag, PropertyAccess, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_method, dbus_property
from PIL import Image

from free_claude_code.cli.desktop import DesktopController
from free_claude_code.cli.desktop_assets import app_icon_bytes

_SNI_INTERFACE = "org.kde.StatusNotifierItem"
_MENU_INTERFACE = "com.canonical.dbusmenu"
_WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"
_WATCHER_NAME = _WATCHER_INTERFACE
_WATCHER_PATH = "/StatusNotifierWatcher"
_ITEM_PATH = "/StatusNotifierItem"
_MENU_PATH = "/MenuBar"
_ITEM_BUS_NAME = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
_PIXMAP_SIZE = 256
_PROBE_TIMEOUT_SECONDS = 2
_LAYOUT_REVISION = 1


@dataclass(frozen=True, slots=True)
class MenuEntry:
    """A DBusMenu item bound to a tray action."""

    item_id: int
    label: str = ""
    action: Callable[[], None] | None = None
    separator: bool = False


@lru_cache(maxsize=1)
def icon_pixmap() -> list[tuple[int, int, bytes]]:
    """Return the branded icon as an SNI IconPixmap payload (ARGB32)."""

    with Image.open(BytesIO(app_icon_bytes(".png"))) as image:
        rgba = image.convert("RGBA").resize(
            (_PIXMAP_SIZE, _PIXMAP_SIZE), Image.Resampling.LANCZOS
        )
        red, green, blue, alpha = rgba.split()
        argb = Image.merge("RGBA", (alpha, red, green, blue)).tobytes()
    return [(_PIXMAP_SIZE, _PIXMAP_SIZE, argb)]


def _dbus_method(
    *, out_signature: str, **parameters: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Tag a plain method with DBus signatures for dbus-fast to introspect.

    dbus-fast derives wire signatures from function annotations, which must be
    raw DBus signature strings (like ``"as"``) that static type checkers
    reject. Methods keep real Python annotations for ``ty``; this decorator
    swaps in the DBus signatures on ``fn.__annotations__`` right before
    dbus-fast reads them.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        annotations = dict(parameters)
        if out_signature:
            annotations["return"] = out_signature
        fn.__annotations__ = annotations
        return dbus_method()(fn)

    return decorator


def _dbus_property(
    signature: str, *, access: PropertyAccess = PropertyAccess.READ
) -> Callable[[Callable[..., Any]], Any]:
    """Tag a plain property getter with its DBus signature (see _dbus_method)."""

    def decorator(fn: Callable[..., Any]) -> Any:
        fn.__annotations__ = {"return": signature}
        return dbus_property(access=access)(fn)

    return decorator


LayoutNode = tuple[int, dict[str, Variant], list[Variant]]


def menu_node(entry: MenuEntry) -> LayoutNode:
    """Build a DBusMenu layout node for one menu entry."""

    if entry.separator:
        properties: dict[str, Variant] = {
            "type": Variant("s", "separator"),
            "visible": Variant("b", True),
        }
    else:
        properties = {
            "label": Variant("s", entry.label),
            "enabled": Variant("b", True),
            "visible": Variant("b", True),
        }
    return (entry.item_id, properties, [])


def layout_root(entries: list[MenuEntry]) -> LayoutNode:
    """Build the root DBusMenu layout node wrapping the given entries."""

    children = [Variant("(ia{sv}av)", menu_node(entry)) for entry in entries]
    return (0, {"children-display": Variant("s", "submenu")}, children)


class StatusNotifierItemInterface(ServiceInterface):
    """Expose the tray item properties the SNI host reads on registration."""

    def __init__(self, menu_path: str) -> None:
        super().__init__(_SNI_INTERFACE)
        self._menu_path = menu_path

    @_dbus_property("s")
    def Category(self) -> str:
        return "ApplicationStatus"

    @_dbus_property("s")
    def Id(self) -> str:
        return "free-claude-code"

    @_dbus_property("s")
    def Title(self) -> str:
        return "Free Claude Code"

    @_dbus_property("s")
    def Status(self) -> str:
        return "Active"

    @_dbus_property("a(iiay)")
    def IconPixmap(self) -> list[tuple[int, int, bytes]]:
        return icon_pixmap()

    @_dbus_property("o")
    def Menu(self) -> str:
        return self._menu_path

    @_dbus_property("b")
    def ItemIsMenu(self) -> bool:
        return False

    @_dbus_property("i")
    def WindowId(self) -> int:
        return 0


class DbusMenuInterface(ServiceInterface):
    """Minimal com.canonical.dbusmenu service for the tray's static menu."""

    def __init__(self, entries: list[MenuEntry]) -> None:
        super().__init__(_MENU_INTERFACE)
        self._entries = entries
        self._by_id = {entry.item_id: entry for entry in entries}

    @_dbus_method(
        out_signature="(i(ia{sv}av))",
        parent_id="i",
        recursion_depth="i",
        property_names="as",
    )
    def GetLayout(
        self, parent_id: int, recursion_depth: int, property_names: list[str]
    ) -> tuple[int, LayoutNode]:
        return (_LAYOUT_REVISION, layout_root(self._entries))

    @_dbus_method(out_signature="a(ia(sv))", ids="ai", property_names="as")
    def GetGroupProperties(
        self, ids: list[int], property_names: list[str]
    ) -> list[tuple[int, list[tuple[str, Variant]]]]:
        selected = [entry for entry in self._entries if entry.item_id in ids]
        return [
            (entry.item_id, list(menu_node(entry)[1].items())) for entry in selected
        ]

    @_dbus_method(out_signature="", item_id="i", event_id="s", data="v", timestamp="u")
    def Event(self, item_id: int, event_id: str, data: object, timestamp: int) -> None:
        if event_id != "clicked":
            return
        entry = self._by_id.get(item_id)
        if entry is not None and entry.action is not None:
            entry.action()

    @_dbus_method(out_signature="b", parent_id="i")
    def AboutToShow(self, parent_id: int) -> bool:
        return True


class StatusNotifierDesktopTray:
    """Serve the FCC Desktop actions through a Wayland StatusNotifierItem."""

    def __init__(self, controller: DesktopController) -> None:
        self._controller = controller
        self._stopped = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._shutdown: asyncio.Event | None = None
        self._entries = [
            MenuEntry(1, "Open", controller.open_admin),
            MenuEntry(2, "Quit", controller.quit),
        ]

    def run(self) -> None:
        """Serve the tray on a DBus worker thread and block until stopped."""

        thread = threading.Thread(
            target=self._serve_dbus, name="fcc-sni-dbus", daemon=True
        )
        thread.start()
        try:
            self._stopped.wait()
        except KeyboardInterrupt:
            self._controller.quit()
        thread.join(timeout=5)

    def stop(self) -> None:
        """End the tray loop and ask the DBus worker to disconnect."""

        self._stopped.set()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._signal_shutdown)

    def _serve_dbus(self) -> None:
        try:
            asyncio.run(self._serve_async())
        except Exception:
            print(
                "FCC Desktop could not register a system tray over DBus; it is "
                "running in background mode without a tray icon. The Admin UI "
                "is available in your browser. Stop FCC Desktop with: "
                "pkill fcc-desktop",
                file=sys.stderr,
            )

    async def _serve_async(self) -> None:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus = bus
        self._loop = asyncio.get_running_loop()
        self._shutdown = asyncio.Event()
        try:
            bus.export(_ITEM_PATH, StatusNotifierItemInterface(_MENU_PATH))
            bus.export(_MENU_PATH, DbusMenuInterface(self._entries))
            await bus.request_name(_ITEM_BUS_NAME, NameFlag.DO_NOT_QUEUE)
            await self._register(bus)
            await self._shutdown.wait()
        finally:
            self._shutdown = None
            self._loop = None
            self._bus = None
            bus.disconnect()

    async def _register(self, bus: MessageBus) -> None:
        """Register this item with the session StatusNotifierWatcher."""

        reply = await bus.call(
            Message(
                destination=_WATCHER_NAME,
                path=_WATCHER_PATH,
                interface=_WATCHER_INTERFACE,
                member="RegisterStatusNotifierItem",
                signature="s",
                body=[_ITEM_PATH],
            )
        )
        if reply.message_type is not MessageType.METHOD_RETURN:
            raise RuntimeError(
                f"StatusNotifierWatcher rejected registration: {reply.error_name}"
            )

    def _signal_shutdown(self) -> None:
        shutdown = self._shutdown
        if shutdown is not None:
            shutdown.set()


async def _probe_watcher() -> bool:
    """Return True when a StatusNotifier host is registered with the watcher."""

    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        reply = await bus.call(
            Message(
                destination=_WATCHER_NAME,
                path=_WATCHER_PATH,
                interface="org.freedesktop.DBus.Properties",
                member="Get",
                signature="ss",
                body=[_WATCHER_INTERFACE, "IsStatusNotifierHostRegistered"],
            )
        )
        if reply.message_type is not MessageType.METHOD_RETURN:
            return False
        return bool(reply.body[0].value)
    finally:
        bus.disconnect()


def sni_host_available() -> bool:
    """Return True when a StatusNotifier host can display the tray."""

    try:
        return asyncio.run(asyncio.wait_for(_probe_watcher(), _PROBE_TIMEOUT_SECONDS))
    except Exception:
        return False
