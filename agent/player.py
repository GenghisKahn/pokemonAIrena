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
    "moves, or `switch <index>` to switch to a benched Pokemon. Pick only from the legal "
    "options given. Prefer super-effective, STAB damage. But SWITCH instead of attacking "
    "when your active is at a bad matchup — the opponent hits it super-effectively and a "
    "benched Pokemon resists that type or threatens back; don't just attack every turn. "
    "Use the recent battle log for context (what was used, damage dealt, stat changes). "
    "No explanation."
)


def _incoming(defender, attacker, kb: KB) -> float:
    """Worst-case STAB multiplier `attacker`'s types land on `defender`."""
    return max((kb.type_multiplier(t, defender.types) for t in attacker.types), default=1.0)


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
        self._history: list[str] = []          # human-readable log of prior turns
        self._prev: tuple[BattleState, Action] | None = None   # last (state, action)

    def decide(self, state: BattleState, kb: KB) -> Action:
        self._record(state)                    # log what happened since our last decision
        try:
            reply = self.provider.complete(_SYSTEM, self._prompt(state, kb))
            action = self._parse(reply, state)
            if action is None:
                action = self.fallback.decide(state, kb)
        except Exception:
            action = self.fallback.decide(state, kb)   # any provider/parse error -> stay legal
        self._prev = (state, action)
        return action

    def _record(self, state: BattleState) -> None:
        """Derive what changed since our last decision (moves used, damage, switches, and
        any reported effects) and append one line to the running battle log the prompt shows."""
        events = list(state.events or ())
        if self._prev is None:
            if events:
                self._history.append("battle start — " + "; ".join(events))
            return
        prev, action = self._prev
        parts: list[str] = []
        if action.kind == "switch":
            parts.append(f"you switched in {state.self_active.name}")
        elif action.index < len(prev.self_active.moves):
            parts.append(f"you used {prev.self_active.moves[action.index].name}")
        if state.opp_active.name != prev.opp_active.name:
            parts.append(f"opponent sent out {state.opp_active.name}")
        else:
            d = prev.opp_active.hp - state.opp_active.hp
            if d > 0:
                parts.append(f"{state.opp_active.name} took {d} ({state.opp_active.hp}/{state.opp_active.max_hp} left)")
            elif d < 0:
                parts.append(f"{state.opp_active.name} recovered {-d}")
        if state.self_active.name == prev.self_active.name:
            d = prev.self_active.hp - state.self_active.hp
            if d > 0:
                parts.append(f"your {state.self_active.name} took {d} ({state.self_active.hp}/{state.self_active.max_hp} left)")
        if events:
            parts.append("effects: " + "; ".join(events))
        if parts:
            self._history.append("; ".join(parts))

    def _prompt(self, state: BattleState, kb: KB) -> str:
        me, opp = state.self_active, state.opp_active
        incoming = _incoming(me, opp, kb)
        lines = [
            f"Your active: {me.name} ({'/'.join(me.types)}) HP {me.hp}/{me.max_hp}"
            + (f" status={me.status}" if me.status else ""),
            f"Opponent: {opp.name} ({'/'.join(opp.types)}) HP {opp.hp}/{opp.max_hp}",
        ]
        if incoming >= 2:
            lines.append(f"WARNING: {opp.name}'s STAB is {incoming:g}x super-effective vs your "
                         f"{me.name} — consider switching to a Pokemon that resists it.")
        lines += ["", "Legal moves:" if state.available_moves else "Legal moves: none"]
        for i in state.available_moves:
            mv = me.moves[i]
            eff = kb.type_multiplier(mv.type, opp.types)
            dmg = estimate_damage(me, opp, mv, kb)
            lines.append(f"  move {i}: {mv.name} ({mv.type}, power {mv.power}, {eff:g}x, ~{dmg} dmg)")
        if state.available_switches:
            lines.append("Legal switches (matchup vs the current opponent):")
            for i in state.available_switches:
                p = state.party[i]
                takes = _incoming(p, opp, kb)                 # opp STAB vs this bench mon
                deals = _incoming(opp, p, kb)                 # this bench mon's STAB vs opp
                tag = "RESISTS" if takes < 1 else ("WEAK to" if takes >= 2 else "neutral vs")
                lines.append(f"  switch {i}: {p.name} ({'/'.join(p.types)}) HP {p.hp}/{p.max_hp} — "
                             f"{tag} {opp.name} (takes {takes:g}x, its STAB hits {opp.name} {deals:g}x)")
        if self._history:
            lines += ["", "Recent battle log (oldest first):"]
            lines += [f"  - {h}" for h in self._history[-6:]]
        lines += ["", "Your choice:"]
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
