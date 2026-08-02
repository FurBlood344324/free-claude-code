"""Tray availability probing and headless fallback contracts."""

import builtins
import sys
import types
from collections.abc import Mapping, Sequence
from unittest.mock import MagicMock

import pytest

from free_claude_code.cli import desktop_tray, sni_tray


class _FakeXlibPackage(types.ModuleType):
    """Module stub whose attributes satisfy static type checking."""

    X: MagicMock


class _FakeXlibDisplayPackage(types.ModuleType):
    """Submodule stub whose attributes satisfy static type checking."""

    Display: MagicMock


def _fake_x11_modules(
    owner: object,
    *,
    display_error: Exception | None = None,
) -> tuple[types.ModuleType, types.ModuleType, MagicMock]:
    fake_x = MagicMock()
    fake_x.NONE = 0
    fake_display = MagicMock()
    fake_display.intern_atom.return_value = 42
    fake_display.get_selection_owner.return_value = owner
    display_factory = MagicMock(return_value=fake_display)
    if display_error is not None:
        display_factory.side_effect = display_error

    xlib_package = _FakeXlibPackage("Xlib")
    xlib_package.X = fake_x
    xlib_display_package = _FakeXlibDisplayPackage("Xlib.display")
    xlib_display_package.Display = display_factory
    return xlib_package, xlib_display_package, fake_display


def test_x11_systray_available_true_when_selection_is_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xlib_package, xlib_display_package, fake_display = _fake_x11_modules(owner=7)
    monkeypatch.setitem(sys.modules, "Xlib", xlib_package)
    monkeypatch.setitem(sys.modules, "Xlib.display", xlib_display_package)

    assert desktop_tray._x11_systray_available() is True
    fake_display.intern_atom.assert_called_once_with("_NET_SYSTEM_TRAY_S0")
    fake_display.close.assert_called_once_with()


def test_x11_systray_available_false_when_selection_is_unowned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xlib_package, xlib_display_package, fake_display = _fake_x11_modules(owner=0)
    monkeypatch.setitem(sys.modules, "Xlib", xlib_package)
    monkeypatch.setitem(sys.modules, "Xlib.display", xlib_display_package)

    assert desktop_tray._x11_systray_available() is False
    fake_display.close.assert_called_once_with()


def test_x11_systray_available_false_when_display_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xlib_package, xlib_display_package, fake_display = _fake_x11_modules(
        owner=0,
        display_error=RuntimeError('Bad display name ""'),
    )
    monkeypatch.setitem(sys.modules, "Xlib", xlib_package)
    monkeypatch.setitem(sys.modules, "Xlib.display", xlib_display_package)

    assert desktop_tray._x11_systray_available() is False
    fake_display.close.assert_not_called()


def test_x11_systray_available_false_when_xlib_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def guarded_import(
        name: str,
        globals_: Mapping[str, object] | None = None,
        locals_: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> object:
        if name == "Xlib" or name.startswith("Xlib."):
            raise ImportError("No module named 'Xlib'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert desktop_tray._x11_systray_available() is False


def test_systray_available_is_true_outside_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop_tray.sys, "platform", "win32")

    assert desktop_tray._systray_available() is True


def test_systray_available_skips_x11_probe_for_gi_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop_tray.sys, "platform", "linux")
    monkeypatch.setattr(desktop_tray.Icon, "__module__", "pystray._appindicator")
    monkeypatch.setattr(desktop_tray, "_x11_systray_available", lambda: False)

    assert desktop_tray._systray_available() is True


def test_systray_available_probes_x11_owner_for_xorg_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop_tray.sys, "platform", "linux")
    monkeypatch.setattr(desktop_tray.Icon, "__module__", "pystray._xorg")
    probe = MagicMock(return_value=True)
    monkeypatch.setattr(desktop_tray, "_x11_systray_available", probe)

    assert desktop_tray._systray_available() is True
    probe.assert_called_once_with()


def test_launch_uses_pystray_when_systray_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[object] = []

    def fake_launch_desktop(tray_factory: object) -> None:
        launched.append(tray_factory)

    monkeypatch.setattr(desktop_tray, "_sni_host_available", lambda: False)
    monkeypatch.setattr(desktop_tray, "_systray_available", lambda: True)
    monkeypatch.setattr(desktop_tray, "launch_desktop", fake_launch_desktop)

    desktop_tray.launch()

    assert launched == [desktop_tray.PystrayDesktopTray]


def test_launch_falls_back_to_headless_without_systray(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    launched: list[object] = []

    def fake_launch_desktop(tray_factory: object) -> None:
        launched.append(tray_factory)

    monkeypatch.setattr(desktop_tray, "_sni_host_available", lambda: False)
    monkeypatch.setattr(desktop_tray, "_systray_available", lambda: False)
    monkeypatch.setattr(desktop_tray, "launch_desktop", fake_launch_desktop)

    desktop_tray.launch()

    assert launched == [desktop_tray.HeadlessDesktopTray]
    assert "system tray" in capsys.readouterr().err


def test_sni_host_available_is_false_outside_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop_tray.sys, "platform", "win32")

    assert desktop_tray._sni_host_available() is False


def test_sni_host_available_probes_sni_host_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = MagicMock(return_value=True)
    monkeypatch.setattr(sni_tray, "sni_host_available", probe)

    assert desktop_tray._sni_host_available() is True
    probe.assert_called_once_with()


def test_sni_host_available_false_when_probe_says_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = MagicMock(return_value=False)
    monkeypatch.setattr(sni_tray, "sni_host_available", probe)

    assert desktop_tray._sni_host_available() is False


def test_launch_prefers_sni_tray_when_host_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[object] = []

    def fake_launch_desktop(tray_factory: object) -> None:
        launched.append(tray_factory)

    monkeypatch.setattr(desktop_tray, "_sni_host_available", lambda: True)
    monkeypatch.setattr(desktop_tray, "launch_desktop", fake_launch_desktop)

    desktop_tray.launch()

    assert launched == [sni_tray.StatusNotifierDesktopTray]
