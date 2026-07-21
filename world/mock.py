"""mock — an in-memory Gen 1 battle engine. No emulator, no ROM.

This is the deterministic default backend: it plays a real 3v3 (type chart, base
stats, RBY damage from the KB) so the whole harness — observe, gate, player,
loop — is exercised and testable end to end. The opponent uses a simple
best-damage AI. Everything is deterministic (max damage roll), so a battle
replays identically every run.

It exposes exactly what RAM would: dex IDs, HP, PP, status. The knowledge base
supplies the meaning, same as against a real emulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from battle.damage import battle_stats, damage_raw
from battle.state import Action
from kb import default_kb


@dataclass
class _Mon:
    name: str
    dex: int
    types: tuple
    stats: dict
    max_hp: int
    hp: int
    moves: list          # [{name, type, power, pp, category}]
    status: str | None = None
    stages: dict = field(default_factory=dict)

    @property
    def fainted(self) -> bool:
        return self.hp <= 0


class MockBattle:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.kb = default_kb()
        self.level = cfg["world"].get("level", 50)
        self.reset()

    # ---- construction -------------------------------------------------------
    def _make_team(self, spec: list) -> list[_Mon]:
        team = []
        for entry in spec:
            sp = self.kb.species(entry["species"])
            stats = battle_stats(sp["base"], self.level)
            moves = []
            for mn in entry["moves"]:
                md = self.kb.move(mn)
                moves.append({"name": mn, "type": md["type"], "power": md["power"],
                              "pp": md["pp"], "category": self.kb.category(md["type"])})
            team.append(_Mon(name=entry["species"], dex=sp["dex"], types=tuple(sp["types"]),
                             stats=stats, max_hp=stats["hp"], hp=stats["hp"], moves=moves))
        return team

    def reset(self) -> None:
        b = self.cfg["battle"]
        self.teams = [self._make_team(b["player_team"]), self._make_team(b["opponent_team"])]
        self.active = [0, 0]
        self.pending: Action | None = None
        self.turns = 0

    # ---- Backend interface --------------------------------------------------
    def _bench_slots(self, side: int) -> list[int]:
        a = self.active[side]
        return [i for i in range(len(self.teams[side])) if i != a]

    def snapshot(self) -> dict:
        me = self.teams[0][self.active[0]]
        opp = self.teams[1][self.active[1]]
        party = [
            {"dex": self.teams[0][s].dex, "hp": self.teams[0][s].hp,
             "max_hp": self.teams[0][s].max_hp, "status": self.teams[0][s].status}
            for s in self._bench_slots(0)
        ]
        return {
            "awaiting": None if self.is_over() else "move",
            "self": {
                "dex": me.dex, "hp": me.hp, "max_hp": me.max_hp, "status": me.status,
                "stages": dict(me.stages),
                "moves": [{"name": mv["name"], "pp": mv["pp"]} for mv in me.moves],
            },
            "self_party": party,
            "opp": {"dex": opp.dex, "hp": opp.hp, "max_hp": opp.max_hp, "status": opp.status},
        }

    def awaiting_input(self) -> bool:
        return not self.is_over()

    def send_action(self, action: Action) -> None:
        self.pending = action

    def step(self) -> None:
        if self.is_over() or self.pending is None:
            self.pending = None
            return
        action, self.pending = self.pending, None
        self.turns += 1

        # Player's action: a switch happens before any attack and forfeits the attack.
        player_move = None
        if action.kind == "switch":
            slots = self._bench_slots(0)
            if 0 <= action.index < len(slots) and not self.teams[0][slots[action.index]].fainted:
                self.active[0] = slots[action.index]
        else:
            me = self.teams[0][self.active[0]]
            if 0 <= action.index < len(me.moves) and me.moves[action.index]["pp"] > 0:
                player_move = me.moves[action.index]

        opp_move = self._opp_choose()

        # Attackers act fastest-first; ties go to the player (stable order). The
        # attacker Mon is bound now, so a mon that faints earlier in the turn is
        # skipped here (its just-switched-in replacement doesn't move until next turn).
        actors = []
        if player_move is not None:
            actors.append((self.teams[0][self.active[0]], 0, player_move))
        if opp_move is not None:
            actors.append((self.teams[1][self.active[1]], 1, opp_move))
        actors.sort(key=lambda a: a[0].stats["spe"], reverse=True)

        for atk, side, move in actors:
            deff = self.teams[1 - side][self.active[1 - side]]  # whoever is now in front
            if atk.fainted or deff.fainted:
                continue
            move["pp"] = max(0, move["pp"] - 1)
            deff.hp = max(0, deff.hp - self._damage(atk, deff, move))
            if deff.fainted:
                self._auto_switch(1 - side)

    def is_over(self) -> bool:
        return any(all(m.fainted for m in team) for team in self.teams)

    def result(self) -> dict:
        p_alive = sum(not m.fainted for m in self.teams[0])
        o_alive = sum(not m.fainted for m in self.teams[1])
        winner = "player" if o_alive == 0 and p_alive else "opponent" if p_alive == 0 and o_alive else None
        return {"winner": winner, "player_remaining": p_alive, "opponent_remaining": o_alive}

    # ---- engine internals ---------------------------------------------------
    def _damage(self, atk: _Mon, deff: _Mon, move: dict) -> int:
        cat = move["category"]
        a = atk.stats["atk"] if cat == "physical" else atk.stats["spc"]
        d = deff.stats["def"] if cat == "physical" else deff.stats["spc"]
        return damage_raw(self.kb, move["type"], move["power"], a, d, atk.types, deff.types, self.level)

    def _opp_choose(self) -> dict | None:
        opp = self.teams[1][self.active[1]]
        me = self.teams[0][self.active[0]]
        best, best_dmg = None, -1
        for mv in opp.moves:
            if mv["pp"] <= 0:
                continue
            dmg = self._damage(opp, me, mv)
            if dmg > best_dmg:
                best_dmg, best = dmg, mv
        return best

    def _auto_switch(self, side: int) -> None:
        for i, m in enumerate(self.teams[side]):
            if not m.fainted:
                self.active[side] = i
                return
