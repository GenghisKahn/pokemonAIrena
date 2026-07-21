"""send_input() — the hands. The ONLY door out of the harness into the game.

Every action passes through here, which is exactly why the guardrail gate sits
just upstream. By the time an action reaches this function it has already been
vetted; send_input just hands it to the backend to actuate (menu navigation on
a real emulator, a resolved turn on the mock).
"""
from __future__ import annotations

from battle.state import Action


def send_input(backend, action: Action) -> None:
    backend.send_action(action)
