"""The turn loop — the harness heartbeat. Wait for input -> observe -> decide ->
gate -> act -> step, until one side has no Pokemon left.

The player only ever proposes; the gate vets; send_input is the single door out.
`max_turns` is a hard cap so a battle can never hang.
"""
from __future__ import annotations

from battle.act import send_input
from battle.observe import read_battle
from battle.state import Action, BattleState
from guardrails import rules
from kb import KB


def _packet(turn: int, state: BattleState, action: Action, blocks: list[str]) -> dict:
    """The per-turn record the reasoning dashboard / decision log consumes."""
    label = (state.self_active.moves[action.index].name
             if action.kind == "move" and action.index < len(state.self_active.moves)
             else f"switch->party[{action.index}]")
    return {
        "turn": turn,
        "self": f"{state.self_active.name} {state.self_active.hp}/{state.self_active.max_hp}",
        "opp": f"{state.opp_active.name} {state.opp_active.hp}/{state.opp_active.max_hp}",
        "action": {"kind": action.kind, "index": action.index, "label": label},
        "blocks": list(blocks),
    }


def battle(backend, player, kb: KB, cfg: dict, emit=None) -> dict:
    """Run one battle. Returns a result summary for scoring/logging.

    `emit`, if given, is called once per turn with a decision packet (dict) — the
    feed the dashboard renders. Optional; headless scoring can leave it None.
    """
    backend.reset()
    max_turns = cfg.get("run", {}).get("max_turns", 300)
    blocks: list[str] = []
    turns = 0

    while turns < max_turns and not backend.is_over():
        if not backend.awaiting_input():
            backend.step()
            continue

        state = read_battle(backend, kb, level=cfg["world"].get("level", 50))
        if state.awaiting is None:
            break

        proposed = player.decide(state, kb)
        verdict = rules.check(state, proposed, kb, cfg)
        if verdict.violations:
            blocks.extend(verdict.violations)
        if emit is not None:
            emit(_packet(turns, state, verdict.action, verdict.violations))

        send_input(backend, verdict.action)
        backend.step()
        turns += 1

    result = backend.result()
    result["turns"] = turns
    result["blocks"] = blocks
    return result
