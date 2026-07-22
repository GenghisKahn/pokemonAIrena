"""read_battle() — the eyes. Turn a backend snapshot (RAM-like fields) into one
schema'd BattleState, enriching every dex ID and move name via the knowledge base.

The backend hands over IDs and numbers; the KB supplies types, stats, and move
data. That split is the whole point — swap the backend, keep the meaning.
"""
from __future__ import annotations

from battle.damage import battle_stats
from battle.state import Action, BattleState, MoveView, PokemonView
from kb import KB


def _pokemon_view(kb: KB, raw: dict, level: int, with_moves: bool) -> PokemonView:
    name = kb.name_for(raw["dex"])
    sp = kb.species(name)
    moves: tuple[MoveView, ...] = ()
    if with_moves:
        mvs = []
        for i, m in enumerate(raw.get("moves", [])):
            data = kb.move(m["name"])
            mvs.append(MoveView(
                name=m["name"],
                type=data["type"],
                power=data["power"],
                category=kb.category(data["type"]),
                accuracy=data["accuracy"],
                pp=m["pp"],
                index=i,
            ))
        moves = tuple(mvs)
    return PokemonView(
        dex=raw["dex"],
        name=name,
        types=tuple(sp["types"]),
        level=level,
        hp=raw["hp"],
        max_hp=raw["max_hp"],
        status=raw.get("status"),
        stages=raw.get("stages", {}),
        stats=battle_stats(sp["base"], level),
        moves=moves,
    )


def read_battle(backend, kb: KB, level: int = 50) -> BattleState:
    snap = backend.snapshot()
    self_active = _pokemon_view(kb, snap["self"], level, with_moves=True)
    opp_active = _pokemon_view(kb, snap["opp"], level, with_moves=False)
    party = tuple(_pokemon_view(kb, p, level, with_moves=False) for p in snap.get("self_party", []))

    available_moves = tuple(mv.index for mv in self_active.moves if mv.pp > 0)
    available_switches = tuple(i for i, p in enumerate(party) if not p.fainted)

    return BattleState(
        self_active=self_active,
        opp_active=opp_active,
        party=party,
        available_moves=available_moves,
        available_switches=available_switches,
        awaiting=snap["awaiting"],
        events=tuple(snap.get("events", ())),
    )
