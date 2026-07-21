"""The verification gate. Every action passes through here before it reaches the game.

Legality is cheap and absolute (the move must exist and have PP; a switch target
must be alive). Quality is judgement the game won't enforce: don't waste a turn on
a 0x-effectiveness move, and flag switching a Pokemon into a super-effective hit.
The gate returns a possibly-substituted action plus the reasons it intervened, so
the harness can log *why*.
"""
from __future__ import annotations

from dataclasses import dataclass

from battle.damage import estimate_damage
from battle.state import Action, BattleState
from kb import KB


@dataclass
class Verdict:
    action: Action            # possibly substituted
    violations: list[str]     # human-readable reasons; empty == clean

    @property
    def ok(self) -> bool:
        return not self.violations


def _best_move(state: BattleState, kb: KB) -> int | None:
    """The legal move slot with the highest expected damage right now."""
    best_i, best_dmg = None, -1
    for i in state.available_moves:
        dmg = estimate_damage(state.self_active, state.opp_active, state.self_active.moves[i], kb)
        if dmg > best_dmg:
            best_dmg, best_i = dmg, i
    return best_i


def _incoming_risk(incoming, opp, kb: KB) -> float:
    """Worst-case STAB multiplier the opponent's types could land on `incoming`."""
    return max((kb.type_multiplier(t, incoming.types) for t in opp.types), default=1.0)


def check(state: BattleState, action: Action, kb: KB, cfg: dict) -> Verdict:
    g = cfg.get("guardrails", {})
    out = action
    tripped: list[str] = []

    if action.kind == "move":
        # Legality: the slot must be a real, PP-having move.
        if action.index not in state.available_moves:
            fallback = state.available_moves[0] if state.available_moves else None
            if fallback is not None:
                tripped.append(f"illegal-move: slot {action.index} unavailable -> {state.self_active.moves[fallback].name}")
                out = Action("move", fallback)
            else:
                return Verdict(out, tripped)  # nothing legal; let the backend handle Struggle

        # Quality: don't throw the turn away on a 0x move if a better one exists.
        if g.get("block_zero_effect", True):
            mv = state.self_active.moves[out.index]
            if kb.type_multiplier(mv.type, state.opp_active.types) == 0:
                best = _best_move(state, kb)
                if best is not None and best != out.index and \
                        estimate_damage(state.self_active, state.opp_active, state.self_active.moves[best], kb) > 0:
                    tripped.append(
                        f"zero-effect: {mv.name} is 0x vs {'/'.join(state.opp_active.types)} "
                        f"-> {state.self_active.moves[best].name}"
                    )
                    out = Action("move", best)

    elif action.kind == "switch":
        # Legality: switch target must be a live bench Pokemon.
        if action.index not in state.available_switches:
            tripped.append(f"illegal-switch: party slot {action.index} unavailable")
            if state.available_moves:
                out = Action("move", state.available_moves[0])
        # Quality: warn (don't block) if it walks into a super-effective hit.
        elif g.get("warn_bad_switch", True):
            incoming = state.party[action.index]
            if _incoming_risk(incoming, state.opp_active, kb) >= 2.0:
                tripped.append(f"bad-switch: {incoming.name} is weak to {state.opp_active.name}")

    return Verdict(out, tripped)
