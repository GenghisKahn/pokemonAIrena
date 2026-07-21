"""The player — decide(state, kb) -> Action.

Two implementations behind one interface:
  * HeuristicPlayer — deterministic, no API. Picks the highest-expected-damage move
    (naturally favouring STAB and super-effective hits), switching only when the
    active mon can't damage the opponent at all. The baseline the LLM must beat, and
    what the deterministic tests exercise.
  * LLMPlayer — asks a model for intent each turn (Claude API or a local llama.cpp
    server, see agent/providers.py). It only ever proposes among the *legal* actions
    in the state; anything unparseable, illegal, or erroring falls back to
    HeuristicPlayer — a battle can never hang on a stalled or invalid turn.
"""
from __future__ import annotations

import re

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


_ACTION_RE = re.compile(r"\b(move|switch)\s+(\d+)\b", re.IGNORECASE)

_SYSTEM = (
    "You are choosing one action in a Gen 1 (Pokemon Stadium) battle. "
    "Reply with EXACTLY one line and nothing else: `move <slot>` to use one of your "
    "moves, or `switch <index>` to switch to a benched Pokemon. Pick only from the "
    "legal options given. Prefer super-effective, STAB damage; switch away from a "
    "bad matchup. No explanation."
)


class LLMPlayer:
    """Ask a model for the move each turn; fall back to the heuristic on any problem.

    The provider (Claude API or local llama.cpp) is built from config.agent, or
    injected for testing. The model's reply is parsed to an Action and validated
    against the legal options; an unparseable, illegal, or erroring reply defers to
    HeuristicPlayer so a turn is never lost.
    """

    def __init__(self, cfg: dict, provider=None):
        self.cfg = cfg
        self.fallback = HeuristicPlayer()
        if provider is None:
            from agent.providers import make_provider
            provider = make_provider(cfg["agent"])
        self.provider = provider

    def decide(self, state: BattleState, kb: KB) -> Action:
        try:
            reply = self.provider.complete(_SYSTEM, self._prompt(state, kb))
            action = self._parse(reply, state)
            if action is not None:
                return action
        except Exception:
            pass  # any provider/network/parse error -> heuristic keeps the turn legal
        return self.fallback.decide(state, kb)

    def _prompt(self, state: BattleState, kb: KB) -> str:
        me, opp = state.self_active, state.opp_active
        lines = [
            f"Your active: {me.name} ({'/'.join(me.types)}) "
            f"HP {me.hp}/{me.max_hp}"
            + (f" status={me.status}" if me.status else ""),
            f"Opponent: {opp.name} ({'/'.join(opp.types)}) HP {opp.hp}/{opp.max_hp}",
            "",
            "Legal moves:" if state.available_moves else "Legal moves: none",
        ]
        for i in state.available_moves:
            mv = me.moves[i]
            eff = kb.type_multiplier(mv.type, opp.types)
            dmg = estimate_damage(me, opp, mv, kb)
            lines.append(
                f"  move {i}: {mv.name} ({mv.type}, power {mv.power}, "
                f"{eff:g}x, ~{dmg} dmg)"
            )
        if state.available_switches:
            lines.append("Legal switches:")
            for i in state.available_switches:
                p = state.party[i]
                lines.append(f"  switch {i}: {p.name} ({'/'.join(p.types)}) "
                             f"HP {p.hp}/{p.max_hp}")
        lines.append("")
        lines.append("Your choice:")
        return "\n".join(lines)

    def _parse(self, reply: str, state: BattleState) -> Action | None:
        m = _ACTION_RE.search(reply or "")
        if not m:
            return None
        kind, index = m.group(1).lower(), int(m.group(2))
        if kind == "move" and index in state.available_moves:
            return Action("move", index)
        if kind == "switch" and index in state.available_switches:
            return Action("switch", index)
        return None   # illegal pick -> caller falls back to heuristic
