"""Keyboard input — the act path for the vision approach, one interface per OS.

RetroArch maps keyboard keys to the RetroPad by default, so we drive the game by
posting real key events. Two drivers behind the same surface (`press`,
`tap_sequence`, `activate`):

  * MacKeyboard     — macOS Quartz CGEvent (virtual keycodes).
  * WindowsKeyboard — Windows SendInput with hardware scancodes (stdlib ctypes, no
    dependency). Scancodes — not virtual keys — are what DirectInput-style emulators
    read reliably.

`make_keyboard(driver)` picks one: 'auto' by platform, or force 'mac' / 'windows'.

RetroArch default keyboard -> RetroPad (the binds these maps assume):
    X -> A     Z -> B     arrows -> D-pad     Enter -> Start     R-Shift -> Select

Permissions / focus:
  * macOS  — grant your terminal (or the Python binary) Accessibility, or the events
    do nothing. RetroArch must be frontmost — call activate() first.
  * Windows — no special permission; activate() best-effort raises the RetroArch
    window. Run the emulator windowed/focused.
"""
from __future__ import annotations

import subprocess
import sys
import time

# ---- macOS: RetroPad button -> Quartz virtual keycode --------------------------
_MAC_KEYCODES = {
    "a": 7,       # X
    "b": 6,       # Z
    "up": 126, "down": 125, "left": 123, "right": 124,
    "start": 36,  # Return
    "select": 60,  # Right Shift
}

# ---- Windows: RetroPad button -> (hardware scancode, is_extended_key) -----------
_WIN_SCANCODES = {
    "a": (0x2D, False),   # X
    "b": (0x2C, False),   # Z
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "start": (0x1C, False),   # Enter
    "select": (0x36, False),  # Right Shift
}


def _win_key(button: str) -> tuple[int, bool]:
    """Scancode + extended-key flag for a RetroPad button (arrows are extended)."""
    if button not in _WIN_SCANCODES:
        raise KeyError(f"unknown button {button!r}; expected one of {sorted(_WIN_SCANCODES)}")
    return _WIN_SCANCODES[button]


class _Keyboard:
    """Common tap timing; subclasses implement _down/_up and activate()."""

    def _down(self, button: str) -> None: ...      # pragma: no cover - per-OS
    def _up(self, button: str) -> None: ...        # pragma: no cover - per-OS
    def activate(self) -> None: ...                # pragma: no cover - per-OS

    def press(self, button: str, hold: float = 0.05) -> None:
        """Tap a RetroPad button once (down, brief hold, up)."""
        self._down(button)
        time.sleep(hold)
        self._up(button)
        time.sleep(0.03)

    def tap_sequence(self, buttons, gap: float = 0.12) -> None:
        """Press several buttons in order (e.g. ['down', 'right', 'a'] to pick a move)."""
        for b in buttons:
            self.press(b)
            time.sleep(gap)


class MacKeyboard(_Keyboard):
    """macOS Quartz CGEvent."""

    def __init__(self) -> None:
        import Quartz
        self._Q = Quartz

    def _post(self, keycode: int, down: bool) -> None:
        ev = self._Q.CGEventCreateKeyboardEvent(None, keycode, down)
        self._Q.CGEventPost(self._Q.kCGHIDEventTap, ev)

    def _key(self, button: str) -> int:
        if button not in _MAC_KEYCODES:
            raise KeyError(f"unknown button {button!r}; expected one of {sorted(_MAC_KEYCODES)}")
        return _MAC_KEYCODES[button]

    def _down(self, button: str) -> None:
        self._post(self._key(button), True)

    def _up(self, button: str) -> None:
        self._post(self._key(button), False)

    def activate(self) -> None:
        subprocess.run(["osascript", "-e", 'tell application "RetroArch" to activate'],
                       capture_output=True)


class WindowsKeyboard(_Keyboard):
    """Windows SendInput with hardware scancodes (stdlib ctypes)."""

    def __init__(self) -> None:
        import ctypes  # noqa: F401
        from ctypes import wintypes  # noqa: F401
        try:
            self._user32 = ctypes.windll.user32   # AttributeError off Windows
        except AttributeError as exc:  # pragma: no cover - platform dependent
            raise RuntimeError("WindowsKeyboard requires Windows (ctypes.windll unavailable).") from exc
        self._ctypes = ctypes
        self._wintypes = wintypes
        self._build_structs()

    def _build_structs(self):  # pragma: no cover - Windows only
        ctypes, wintypes = self._ctypes, self._wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class _INPUTunion(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

        self._KEYBDINPUT, self._INPUT = KEYBDINPUT, INPUT

    def _send(self, button: str, keyup: bool) -> None:  # pragma: no cover - Windows only
        scan, extended = _win_key(button)
        KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP, KEYEVENTF_EXTENDEDKEY = 0x0008, 0x0002, 0x0001
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) \
            | (KEYEVENTF_KEYUP if keyup else 0)
        ki = self._KEYBDINPUT(0, scan, flags, 0, None)
        inp = self._INPUT()
        inp.type = 1                      # INPUT_KEYBOARD
        inp.u.ki = ki
        self._user32.SendInput(1, self._ctypes.byref(inp), self._ctypes.sizeof(inp))

    def _down(self, button: str) -> None:  # pragma: no cover - Windows only
        self._send(button, keyup=False)

    def _up(self, button: str) -> None:  # pragma: no cover - Windows only
        self._send(button, keyup=True)

    def activate(self) -> None:  # pragma: no cover - Windows only
        """Best-effort: bring a RetroArch window to the foreground (non-fatal)."""
        try:
            EnumWindows = self._user32.EnumWindows
            GetWindowTextW, GetWindowTextLengthW = self._user32.GetWindowTextW, self._user32.GetWindowTextLengthW
            SetForegroundWindow = self._user32.SetForegroundWindow
            found = []

            @self._ctypes.WINFUNCTYPE(self._wintypes.BOOL, self._wintypes.HWND, self._wintypes.LPARAM)
            def _cb(hwnd, _lparam):
                n = GetWindowTextLengthW(hwnd)
                buf = self._ctypes.create_unicode_buffer(n + 1)
                GetWindowTextW(hwnd, buf, n + 1)
                if "RetroArch" in buf.value:
                    found.append(hwnd)
                    return False
                return True

            EnumWindows(_cb, 0)
            if found:
                SetForegroundWindow(found[0])
        except Exception:
            pass


def make_keyboard(driver: str = "auto") -> _Keyboard:
    """Build the keyboard driver. 'auto' picks by platform; force 'mac' or 'windows'."""
    if driver == "auto":
        driver = {"darwin": "mac", "win32": "windows"}.get(sys.platform)
        if driver is None:
            raise RuntimeError(
                f"no keyboard driver for platform {sys.platform!r} — force 'mac' or 'windows'"
            )
    if driver == "mac":
        return MacKeyboard()
    if driver == "windows":
        return WindowsKeyboard()
    raise ValueError(f"unknown keyboard driver {driver!r} (expected 'auto', 'mac', or 'windows')")
