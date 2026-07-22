"""Keyboard driver selection and the Windows scancode mapping. We never call
press()/tap_sequence() on a real driver here — that would post live key events into
the machine — only the pure mapping and the factory routing."""
from __future__ import annotations

import sys

import pytest

from world.keyboard import MacKeyboard, _win_key, make_keyboard


def test_win_key_mapping():
    # This RetroArch config (user-confirmed live): A button <- Z key, B button <- A key.
    assert _win_key("a") == (0x2C, False)         # A button = Z key, not extended
    assert _win_key("b") == (0x1E, False)         # B button = A key
    assert _win_key("up") == (0x48, True)         # arrow keys are extended
    assert _win_key("dia_up") == (0x49, True)     # move diamond ▲ = PgUp (extended)
    assert _win_key("start") == (0x1C, False)     # Enter
    with pytest.raises(KeyError):
        _win_key("turbo")


def test_make_keyboard_rejects_unknown():
    with pytest.raises(ValueError) as exc:
        make_keyboard("joystick")
    assert "joystick" in str(exc.value)


@pytest.mark.skipif(sys.platform != "darwin", reason="mac driver needs Quartz")
def test_auto_picks_mac_on_macos():
    assert isinstance(make_keyboard("auto"), MacKeyboard)


def test_windows_driver_errors_off_windows():
    # Forcing 'windows' on a non-Windows host must raise clearly, not import-crash.
    if sys.platform == "win32":
        pytest.skip("on Windows the driver constructs")
    with pytest.raises(RuntimeError) as exc:
        make_keyboard("windows")
    assert "Windows" in str(exc.value)
