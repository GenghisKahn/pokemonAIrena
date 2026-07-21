"""project64 — Windows backend via the Project64 scripting API.

The tidiest of the three: one JS script reads memory (mem.u8 / u16 / u32), wakes
on memory-access callbacks (onread / onwrite) for turn detection, and presses
buttons (joypad.set) for input. This class is the Python side of a small local
bridge to that script (host/port in config.world.project64).

Stubbed until the bridge + RAM map exist. Runs only on Windows.
"""
from __future__ import annotations

from battle.state import Action

_NOT_READY = (
    "Project64 backend is a stub. Stand up the JS-script bridge (mem reads + "
    "joypad input + a local socket), define the battle-struct RAM map, and "
    "implement these against it. Use world.backend: mock until then."
)


class Project64Backend:
    def __init__(self, cfg: dict):
        pj = cfg["world"].get("project64", {})
        self.host = pj.get("host", "127.0.0.1")
        self.port = pj.get("port", 8082)

    def reset(self) -> None:
        raise NotImplementedError(_NOT_READY)

    def snapshot(self) -> dict:
        raise NotImplementedError(_NOT_READY)

    def awaiting_input(self) -> bool:
        raise NotImplementedError(_NOT_READY)

    def send_action(self, action: Action) -> None:
        raise NotImplementedError(_NOT_READY)

    def step(self) -> None:
        raise NotImplementedError(_NOT_READY)

    def is_over(self) -> bool:
        raise NotImplementedError(_NOT_READY)

    def result(self) -> dict:
        raise NotImplementedError(_NOT_READY)
