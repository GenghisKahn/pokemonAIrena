"""The player — decide(state, kb) -> Action.

Two implementations behind one interface:
  * HeuristicPlayer — deterministic, no API. Picks the highest-expected-damage move
    (naturally favouring STAB and super-effective hits), switching only when the
    active mon can't damage the opponent at all. The baseline the LLM must beat, and
    what the deterministic tests exercise.
  * LLMPlayer — asks Claude for intent each turn (stub; wire to config.agent), and
    MUST fall back to HeuristicPlayer on any API error — a battle can never hang.
"""
from __future__ import annotations

from battle.damage import estimate_damage
from battle.state import Action, BattleState
from kb import KB


def make_player(cfg: dict):
    kind = cfg["agent"]["player"]
    if kind == "heuristic":
        return HeuristicPlayer()
    if kind == "llm":
        return LLMPlayer(cfg)
    raise ValueError(f"unknown agent.player: {kind!r} (expected 'heuristic' or 'llm')")


class HeuristicPlayer:
    def decide(self, state: BattleState, kb: KB) -> Action:
        # Forced to switch (active fainted): pick the best matchup on the bench.
        if state.awaiting == "switch" or not state.available_moves:
            target = self._best_switch(state, kb)
            if target is not None:
                return Action("switch", target)
            return Action("move", state.available_moves[0] if state.available_moves else 0)

        best_i, best_dmg = None, -1
        for i in state.available_moves:
            dmg = estimate_damage(state.self_active, state.opp_active, state.self_active.moves[i], kb)
            if dmg > best_dmg:
                best_dmg, best_i = dmg, i

        # If we can't scratch them, look for a bench mon that can.
        if best_dmg <= 0 and state.available_switches:
            target = self._best_switch(state, kb)
            if target is not None:
                return Action("switch", target)

        return Action("move", best_i if best_i is not None else state.available_moves[0])

    def _best_switch(self, state: BattleState, kb: KB) -> int | None:
        """Bench mon whose best STAB does the most to the opponent (proxy for matchup)."""
        best_i, best_score = None, -1.0
        for i in state.available_switches:
            mon = state.party[i]
            score = max((kb.type_multiplier(t, state.opp_active.types) for t in mon.types), default=1.0)
            if score > best_score:
                best_score, best_i = score, i
        return best_i


class LLMPlayer:
    """Stub: ask Claude for a move each turn. Wire to config.agent.model.

    Keep it a choice among the *legal* actions in the state, respect
    config.agent.token_budget, and fall back to HeuristicPlayer on any API error.
    Use player: heuristic until this is implemented.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.fallback = HeuristicPlayer()

    def decide(self, state: BattleState, kb: KB) -> Action:
        raise NotImplementedError(
            "LLMPlayer is a stub. Build a prompt from the BattleState, ask "
            f"{self.cfg['agent']['model']} to choose among available_moves / "
            "available_switches, parse to an Action, and fall back to "
            "self.fallback.decide(state, kb) on any error."
        )
