"""The one interface every backend implements. The harness talks only to this,
so mock vs. Project64 vs. RetroArch is a config choice, not a code change.

A backend exposes battle state as RAM-like fields (`snapshot`), tells the harness
when a decision is needed (`awaiting_input`), and actuates an action (`send_action`).
`step` advances one turn; `is_over` / `result` close out the battle.
"""
from __future__ import annotations

from typing import Protocol

from battle.state import Action


class Backend(Protocol):
    def reset(self) -> None:
        """Return to the battle's start state."""
        ...

    def snapshot(self) -> dict:
        """RAM-like battle fields (dex IDs + numbers) for read_battle() to enrich."""
        ...

    def awaiting_input(self) -> bool:
        """True when the game is waiting for the player to choose (turn detection)."""
        ...

    def send_action(self, action: Action) -> None:
        """Actuate the vetted action (menu navigation on an emulator; queue on mock)."""
        ...

    def step(self) -> None:
        """Advance one turn (resolve it on the mock; let frames run on an emulator)."""
        ...

    def is_over(self) -> bool:
        ...

    def result(self) -> dict:
        ...


def make_backend(cfg: dict) -> Backend:
    """Factory: build the backend named in config.yaml (world.backend)."""
    name = cfg["world"]["backend"]
    if name == "mock":
        from world.mock import MockBattle
        return MockBattle(cfg)
    if name == "project64":
        from world.project64 import Project64Backend
        return Project64Backend(cfg)
    if name == "retroarch":
        from world.retroarch import RetroArchBackend
        return RetroArchBackend(cfg)
    raise ValueError(f"unknown world.backend: {name!r} (expected 'mock', 'project64', or 'retroarch')")
