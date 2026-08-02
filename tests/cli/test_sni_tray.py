"""StatusNotifierItem tray adapter contracts."""

import asyncio
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from dbus_fast import Message, MessageType, Variant

from free_claude_code.cli import sni_tray
from free_claude_code.cli.sni_tray import (
    DbusMenuInterface,
    MenuEntry,
    StatusNotifierDesktopTray,
    StatusNotifierItemInterface,
    icon_pixmap,
    layout_root,
    menu_node,
)


def _invoke(interface: object, name: str, *args: object) -> Any:
    """Call the original method behind a dbus-fast wrapped dispatch."""

    wrapped = getattr(type(interface), name)
    method = wrapped.__dict__["__DBUS_METHOD"]
    return method.fn(interface, *args)


def test_icon_pixmap_returns_single_argb32_pixmap() -> None:
    pixmaps = icon_pixmap()
    assert len(pixmaps) == 1
    width, height, argb = pixmaps[0]
    assert (width, height) == (256, 256)
    assert len(argb) == 256 * 256 * 4
    assert icon_pixmap() is pixmaps


def test_item_properties_expose_sni_identity() -> None:
    interface = StatusNotifierItemInterface("/MenuBar")
    assert interface.Category == "ApplicationStatus"
    assert interface.Id == "free-claude-code"
    assert interface.Title == "Free Claude Code"
    assert interface.Status == "Active"
    assert interface.Menu == "/MenuBar"
    assert interface.ItemIsMenu is False
    assert interface.WindowId == 0
    assert interface.IconPixmap == icon_pixmap()


def test_menu_node_action_entry() -> None:
    item_id, properties, children = menu_node(MenuEntry(1, "Open Admin"))
    assert item_id == 1
    assert children == []
    assert properties["label"].value == "Open Admin"
    assert properties["enabled"].value is True
    assert properties["visible"].value is True
    assert "type" not in properties


def test_menu_node_separator() -> None:
    item_id, properties, children = menu_node(MenuEntry(4, separator=True))
    assert item_id == 4
    assert children == []
    assert properties["type"].value == "separator"
    assert properties["visible"].value is True
    assert "label" not in properties


def test_layout_root_wraps_entries_as_children() -> None:
    entries = [MenuEntry(1, "Open Admin"), MenuEntry(4, separator=True)]
    item_id, properties, children = layout_root(entries)
    assert item_id == 0
    assert properties["children-display"].value == "submenu"
    assert len(children) == 2
    assert children[0].value[0] == 1
    assert children[1].value[0] == 4


def test_get_layout_reports_menu_tree() -> None:
    menu = DbusMenuInterface([MenuEntry(1, "Open Admin"), MenuEntry(5, "Quit")])
    revision, layout = _invoke(menu, "GetLayout", 0, 1, [])
    assert revision == 1
    assert layout[0] == 0
    assert len(layout[2]) == 2


def test_get_group_properties_returns_requested_entries() -> None:
    menu = DbusMenuInterface([MenuEntry(1, "Open Admin"), MenuEntry(5, "Quit")])
    groups = _invoke(menu, "GetGroupProperties", [1, 99], [])
    assert [group[0] for group in groups] == [1]
    labels = [
        value.value for _, pairs in groups for key, value in pairs if key == "label"
    ]
    assert labels == ["Open Admin"]


def test_event_clicked_invokes_entry_action() -> None:
    action = MagicMock()
    menu = DbusMenuInterface([MenuEntry(1, "Open Admin", action)])
    _invoke(menu, "Event", 1, "clicked", None, 0)
    action.assert_called_once_with()


def test_event_ignores_other_events_and_unknown_ids() -> None:
    action = MagicMock()
    menu = DbusMenuInterface([MenuEntry(1, "Open Admin", action)])
    _invoke(menu, "Event", 1, "opened", None, 0)
    action.assert_not_called()
    _invoke(menu, "Event", 99, "clicked", None, 0)
    action.assert_not_called()


def test_about_to_show_is_true() -> None:
    menu = DbusMenuInterface([])
    assert _invoke(menu, "AboutToShow", 0) is True


def test_tray_entries_mirror_pystray_menu() -> None:
    controller = MagicMock()
    tray = StatusNotifierDesktopTray(controller)
    assert [entry.item_id for entry in tray._entries] == [1, 2, 3, 4, 5]
    assert [entry.label for entry in tray._entries] == [
        "Open Admin",
        "Check Server Status",
        "Restart Server",
        "",
        "Quit",
    ]
    assert [entry.separator for entry in tray._entries] == [
        False,
        False,
        False,
        True,
        False,
    ]
    assert tray._entries[0].action == controller.open_admin
    assert tray._entries[2].action == controller.restart_server
    assert tray._entries[4].action == controller.quit
    assert tray._entries[3].action is None


def test_check_status_without_loop_is_noop() -> None:
    tray = StatusNotifierDesktopTray(MagicMock())
    assert tray._loop is None
    tray._check_status()  # must not raise


class _FakeLoop:
    def __init__(self) -> None:
        self.callbacks: list[Callable[[], None]] = []

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        self.callbacks.append(callback)


def test_check_status_schedules_notification_via_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray = StatusNotifierDesktopTray(MagicMock())
    loop = _FakeLoop()
    monkeypatch.setattr(tray, "_loop", loop)
    tray._check_status()
    assert len(loop.callbacks) == 1


class _RecordingBus:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def call(self, message: Message) -> Message:
        self.messages.append(message)
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)


def test_notify_status_sends_desktop_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.status = "running"
    tray = StatusNotifierDesktopTray(controller)
    bus = _RecordingBus()
    monkeypatch.setattr(tray, "_bus", bus)
    asyncio.run(tray._notify_status_async())
    assert len(bus.messages) == 1
    message = bus.messages[0]
    assert message.destination == "org.freedesktop.Notifications"
    assert message.path == "/org/freedesktop/Notifications"
    assert message.interface == "org.freedesktop.Notifications"
    assert message.member == "Notify"
    assert message.body[4] == "Server is running."


class _FailingBus:
    async def call(self, message: Message) -> Message:
        raise OSError("no notification daemon")


def test_notify_status_swallows_bus_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray = StatusNotifierDesktopTray(MagicMock())
    monkeypatch.setattr(tray, "_bus", _FailingBus())
    asyncio.run(tray._notify_status_async())  # must not raise


def test_notify_status_without_bus_is_noop() -> None:
    tray = StatusNotifierDesktopTray(MagicMock())
    asyncio.run(tray._notify_status_async())  # must not raise


def test_send_status_notification_schedules_notify_task() -> None:
    tray = StatusNotifierDesktopTray(MagicMock())

    async def scenario() -> None:
        tray._send_status_notification()
        await asyncio.sleep(0)

    asyncio.run(scenario())  # must not raise


class _FakeBus:
    def __init__(self, **kwargs: object) -> None:
        self.exported: list[tuple[str, object]] = []
        self.registered: Message | None = None
        self.requested_names: list[str] = []
        self.disconnected = False

    async def connect(self) -> _FakeBus:
        return self

    def export(self, path: str, interface: object) -> None:
        self.exported.append((path, interface))

    async def request_name(self, name: str, flags: object) -> None:
        self.requested_names.append(name)

    async def call(self, message: Message) -> Message:
        self.registered = message
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)

    def disconnect(self) -> None:
        self.disconnected = True


def test_serve_async_exports_item_and_menu_then_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = _FakeBus()
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    tray = StatusNotifierDesktopTray(MagicMock())

    async def scenario() -> None:
        task = asyncio.create_task(tray._serve_async())
        await asyncio.sleep(0)
        tray._signal_shutdown()
        await task

    asyncio.run(scenario())

    assert [path for path, _ in bus.exported] == [
        "/StatusNotifierItem",
        "/MenuBar",
    ]
    assert bus.requested_names == [f"org.kde.StatusNotifierItem-{os.getpid()}-1"]
    assert bus.registered is not None
    assert bus.registered.member == "RegisterStatusNotifierItem"
    assert bus.registered.body == ["/StatusNotifierItem"]
    assert bus.disconnected is True
    assert tray._bus is None
    assert tray._loop is None


def test_serve_async_registration_rejection_stops_tray(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _RejectingBus(_FakeBus):
        async def call(self, message: Message) -> Message:
            return Message(
                message_type=MessageType.ERROR,
                error_name="org.freedesktop.DBus.Error.ServiceUnknown",
                reply_serial=1,
            )

    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: _RejectingBus())
    tray = StatusNotifierDesktopTray(MagicMock())
    tray._serve_dbus()
    assert "could not register a system tray" in capsys.readouterr().err


def test_run_blocks_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = _FakeBus()
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    tray = StatusNotifierDesktopTray(MagicMock())
    finished: list[bool] = []
    worker = threading.Thread(target=lambda: (tray.run(), finished.append(True)))
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while tray._bus is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert tray._bus is not None
    finally:
        tray.stop()
        worker.join(timeout=5)
    assert finished == [True]
    assert not worker.is_alive()


def test_run_stop_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = _FakeBus()
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    tray = StatusNotifierDesktopTray(MagicMock())
    tray.stop()
    tray.stop()  # must not raise before the loop exists


class _ReplyBus:
    def __init__(self, reply: Message) -> None:
        self._reply = reply
        self.disconnected = False

    async def connect(self) -> _ReplyBus:
        return self

    async def call(self, message: Message) -> Message:
        self.messages = [message]
        return self._reply

    def disconnect(self) -> None:
        self.disconnected = True


def test_sni_host_available_true_when_host_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = Message(
        message_type=MessageType.METHOD_RETURN,
        reply_serial=1,
        signature="v",
        body=[Variant("b", True)],
    )
    bus = _ReplyBus(reply)
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    assert sni_tray.sni_host_available() is True
    assert bus.disconnected is True
    probe = bus.messages[0]
    assert probe.destination == "org.kde.StatusNotifierWatcher"
    assert probe.path == "/StatusNotifierWatcher"
    assert probe.interface == "org.freedesktop.DBus.Properties"
    assert probe.member == "Get"
    assert probe.body == [
        "org.kde.StatusNotifierWatcher",
        "IsStatusNotifierHostRegistered",
    ]


def test_sni_host_available_false_when_no_host_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = Message(
        message_type=MessageType.METHOD_RETURN,
        reply_serial=1,
        signature="v",
        body=[Variant("b", False)],
    )
    bus = _ReplyBus(reply)
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    assert sni_tray.sni_host_available() is False


def test_sni_host_available_false_when_watcher_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = Message(
        message_type=MessageType.ERROR,
        error_name="org.freedesktop.DBus.Error.ServiceUnknown",
        reply_serial=1,
    )
    bus = _ReplyBus(reply)
    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: bus)
    assert sni_tray.sni_host_available() is False


def test_sni_host_available_false_when_bus_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenBus:
        async def connect(self) -> _BrokenBus:
            raise ConnectionError("no session bus")

    monkeypatch.setattr(sni_tray, "MessageBus", lambda **kwargs: _BrokenBus())
    assert sni_tray.sni_host_available() is False


def test_sni_host_available_false_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never() -> bool:
        await asyncio.sleep(3600)
        return True

    monkeypatch.setattr(sni_tray, "_probe_watcher", never)
    monkeypatch.setattr(sni_tray, "_PROBE_TIMEOUT_SECONDS", 0.01)
    assert sni_tray.sni_host_available() is False
