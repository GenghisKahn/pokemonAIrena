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

# ---- macOS: game key -> Quartz virtual keycode ---------------------------------
# NB: the RetroPad→N64 map for this ROM is NON-STANDARD (live-verified 2026-07-22 via
# RetroArch's Port 1 Controls). The face keys x/a/s are N64 C-buttons, NOT N64 A. The
# names below describe what a key ACTUALLY does in a Stadium battle, not the cfg label.
_MAC_KEYCODES = {
    "select": 6,     # Z  -> opens the move/party "diamond" (the pre-commit screen)
    "check": 13,     # W  -> R/Check: HOLD to preview the diamond's option names
    "cancel": 12,    # Q  -> L/Cancel: back out of the diamond
    "start": 36,     # Return -> N64 Start (Stadium: field/look screen)
    # the four diamond directions == N64 C-buttons; press one (after "select") to commit
    "c_up": 45,      # N -> C-up
    "c_down": 46,    # M -> C-down
    "c_left": 11,    # B -> C-left
    "c_right": 37,   # L -> C-right
    "up": 126, "down": 125, "left": 123, "right": 124,
    # legacy aliases (older code/tests): a=X, b=Z, l=Q, r=W
    "a": 7, "b": 6, "l": 12, "r": 13,
}
_DIR_TO_C = {"up": "c_up", "down": "c_down", "left": "c_left", "right": "c_right"}

# ---- Windows: game key -> (hardware scancode, is_extended_key) ------------------
_WIN_SCANCODES = {
    "select": (0x2C, False),   # Z
    "check": (0x11, False),    # W
    "cancel": (0x10, False),   # Q
    "start": (0x1C, False),    # Enter
    "c_up": (0x31, False),     # N
    "c_down": (0x32, False),   # M
    "c_left": (0x30, False),   # B
    "c_right": (0x26, False),  # L
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "a": (0x2D, False), "b": (0x2C, False), "l": (0x10, False), "r": (0x11, False),
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

    def press(self, button: str, hold: float = 0.3) -> None:
        """Tap a RetroPad button once (down, hold, up).

        The hold is long (0.3s) on purpose: RetroArch reads *core* input by polling a
        key-state array each frame, so a too-brief synthetic press is missed between polls.
        Verified live 2026-07-21 — a 50ms hold did nothing; 0.3-0.35s registers. Hotkeys
        (F1 etc.) are edge-triggered and fire on any hold, but core buttons need this."""
        self._down(button)
        time.sleep(hold)
        self._up(button)
        time.sleep(0.05)

    def tap_sequence(self, buttons, gap: float = 0.12) -> None:
        """Press several buttons in order (e.g. ['down', 'right', 'a'] to pick a move)."""
        for b in buttons:
            self.press(b)
            time.sleep(gap)

    def hold(self, button: str, dur: float = 1.5) -> None:
        """Hold a button down for `dur` seconds — e.g. 'check' (w) to preview the diamond's
        option names (the moves / the party) before committing."""
        self._down(button)
        time.sleep(dur)
        self._up(button)
        time.sleep(0.05)

    def diamond_select(self, direction: str, settle: float = 1.6) -> None:
        """Commit one option from the Stadium move/party 'diamond'. THE core act primitive
        (live-verified 2026-07-22): 'select' (Z) opens the pre-commit screen, then the
        C-button for `direction` (up/down/left/right) chooses that cell — the SAME mechanic
        for both moves and switches. Requires the mouse to be moving (MacKeyboard runs a
        persistent mover). Callers should retry until observe confirms the effect."""
        if direction not in _DIR_TO_C:
            raise ValueError(f"direction must be one of {sorted(_DIR_TO_C)}, got {direction!r}")
        self.press("select")
        time.sleep(settle)
        self.press(_DIR_TO_C[direction])


class MacKeyboard(_Keyboard):
    """macOS Quartz CGEvent, posted directly to the RetroArch process.

    Verified live 2026-07-21: a *global* post (CGEventPost to the HID tap) never reaches
    RetroArch — our own event tap catches the synthetic key but RetroArch ignores it
    (pause_nonactive + its cocoa driver reads per-window events). Posting to RetroArch's
    pid with CGEventPostToPid *does* reach it. So we resolve the pid and target it."""

    def __init__(self, move_mouse: bool = True) -> None:
        import Quartz
        self._Q = Quartz
        self._pid = self._retroarch_pid()
        # pyobjc resolves symbols lazily and NOT thread-safely — touch every Quartz name the
        # mouse thread will use here, on the main thread, so the background thread never
        # triggers a concurrent lazy import (which corrupts pyobjc's funcmap).
        for _name in ("CGWindowListCopyWindowInfo", "CGWarpMouseCursorPosition",
                      "CGEventCreateMouseEvent", "CGEventCreateKeyboardEvent",
                      "CGEventPostToPid", "kCGWindowListOptionOnScreenOnly",
                      "kCGWindowListExcludeDesktopElements", "kCGNullWindowID",
                      "kCGEventMouseMoved", "kCGHIDEventTap", "kCGMouseButtonLeft"):
            getattr(Quartz, _name, None)
        # RetroArch throttles rendering/input processing when the mouse is idle (App-Nap-
        # like). A persistent mover keeps it live so synthetic keys actually register — the
        # single biggest reliability fix (verified 2026-07-22). Runs for the driver's life.
        self._mouse_stop = None
        if move_mouse:
            import threading
            self._mouse_stop = threading.Event()
            threading.Thread(target=self._mouse_loop, daemon=True).start()

    def _window_center(self):
        Q = self._Q
        infos = Q.CGWindowListCopyWindowInfo(
            Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements,
            Q.kCGNullWindowID)
        for w in infos or []:
            if w.get("kCGWindowOwnerName") == "RetroArch":
                b = w["kCGWindowBounds"]
                return b["X"] + b["Width"] / 2, b["Y"] + b["Height"] / 2
        return None

    def _mouse_loop(self) -> None:  # pragma: no cover - live only
        Q, i, center = self._Q, 0, None
        while not self._mouse_stop.is_set():
            if i % 50 == 0:
                center = self._window_center()          # re-resolve (window may move)
            if center is not None:
                dx = ((i * 11) % 60) - 30
                pt = (center[0] + dx, center[1])
                Q.CGWarpMouseCursorPosition(pt)
                if self._pid is not None:
                    Q.CGEventPostToPid(self._pid, Q.CGEventCreateMouseEvent(
                        None, Q.kCGEventMouseMoved, pt, 0))
            i += 1
            time.sleep(0.02)

    def stop(self) -> None:
        if self._mouse_stop is not None:
            self._mouse_stop.set()

    @staticmethod
    def _retroarch_pid() -> int | None:
        try:
            out = subprocess.check_output(["pgrep", "-x", "RetroArch"]).split()
            return int(out[0]) if out else None
        except (subprocess.CalledProcessError, ValueError, IndexError):
            return None

    def _post(self, keycode: int, down: bool) -> None:
        ev = self._Q.CGEventCreateKeyboardEvent(None, keycode, down)
        if self._pid is None or self._retroarch_pid() != self._pid:
            self._pid = self._retroarch_pid()   # RetroArch may have (re)started
        if self._pid is not None:
            self._Q.CGEventPostToPid(self._pid, ev)
        else:                                   # no RetroArch found; fall back to global
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
