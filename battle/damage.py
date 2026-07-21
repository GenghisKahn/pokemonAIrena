"""Gen 1 stat + damage math. Deterministic by default (roll=1.0) so tests are stable.

This is code, never an LLM call. The formulas model Gen 1 / Stadium: a single
Special stat, category fixed by move type, and the classic RBY damage equation.
"""
from __future__ import annotations

import math

from kb import KB


def gen1_stat(base: int, level: int = 50, is_hp: bool = False,
              dv: int = 15, stat_exp: int = 65535) -> int:
    """Gen 1 stat at a level with maxed DV/stat-experience (rental-Pokemon-ish).

    HP adds level+10; other stats add 5. floor(sqrt(stat_exp)/4) caps at 63.
    """
    ev = math.isqrt(stat_exp) // 4
    core = ((base + dv) * 2 + ev) * level // 100
    return core + level + 10 if is_hp else core + 5


def battle_stats(base: dict, level: int = 50) -> dict:
    """All five computed stats for a species' base stats at a level."""
    return {k: gen1_stat(base[k], level, is_hp=(k == "hp")) for k in ("hp", "atk", "def", "spc", "spe")}


def damage_raw(kb: KB, move_type: str, power: int, a_stat: int, d_stat: int,
               attacker_types, defender_types, level: int = 50, roll: float = 1.0) -> int:
    """Core RBY damage equation. roll in [0.85, 1.0]; 1.0 is the max (deterministic)."""
    if power <= 0:
        return 0
    base = (((2 * level // 5 + 2) * power * a_stat // d_stat) // 50) + 2
    stab = 1.5 if move_type.lower() in {t.lower() for t in attacker_types} else 1.0
    eff = kb.type_multiplier(move_type, defender_types)
    return int(base * stab * eff * roll)


def estimate_damage(attacker, defender, move, kb: KB, roll: float = 1.0, level: int = 50) -> int:
    """Expected damage of `move` from attacker -> defender (PokemonView inputs)."""
    cat = kb.category(move.type)
    a = attacker.stats["atk"] if cat == "physical" else attacker.stats["spc"]
    d = defender.stats["def"] if cat == "physical" else defender.stats["spc"]
    return damage_raw(kb, move.type, move.power, a, d, attacker.types, defender.types, level, roll)
