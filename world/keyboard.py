"""Keyboard input — the act path for the vision approach.

RetroArch maps keyboard keys to the RetroPad by default, so we drive the game by
posting real key events (macOS Quartz CGEvent). No RAM write, no virtual gamepad.

RetroArch default keyboard -> RetroPad (the mapping these keycodes assume):
    X -> A     Z -> B     arrows -> D-pad     Enter -> Start     R-Shift -> Select

REQUIRES Accessibility permission: grant your terminal (or the Python binary)
System Settings > Privacy & Security > Accessibility, or the events do nothing.
RetroArch must be the frontmost window — call activate_retroarch() first.
"""
from __future__ import annotations

import subprocess
import time

try:
    import Quartz
    _HAVE_QUARTZ = True
except Exception:  # pragma: no cover
    _HAVE_QUARTZ = False

# RetroPad button -> macOS virtual keycode (RetroArch default keyboard binds).
KEYCODES = {
    "a": 7,       # X
    "b": 6,       # Z
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
    "start": 36,  # Return
    "select": 60,  # Right Shift
}


def _post(keycode: int, down: bool) -> None:
    ev = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def press(button: str, hold: float = 0.05) -> None:
    """Tap a RetroPad button once (key down, brief hold, key up)."""
    if not _HAVE_QUARTZ:
        raise RuntimeError("Quartz unavailable: pip install pyobjc-framework-Quartz")
    if button not in KEYCODES:
        raise KeyError(f"unknown button {button!r}; expected one of {sorted(KEYCODES)}")
    kc = KEYCODES[button]
    _post(kc, True)
    time.sleep(hold)
    _post(kc, False)
    time.sleep(0.03)


def tap_sequence(buttons, gap: float = 0.12) -> None:
    """Press several buttons in order (e.g. ['down', 'right', 'a'] to pick a move)."""
    for b in buttons:
        press(b)
        time.sleep(gap)


def activate_retroarch() -> None:
    """Bring RetroArch to the front so it receives the key events."""
    subprocess.run(["osascript", "-e", 'tell application "RetroArch" to activate'],
                   capture_output=True)
