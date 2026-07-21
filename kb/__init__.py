"""The knowledge base — the meaning RAM doesn't give you.

RAM stores dex IDs and numbers. The KB turns those into types, base stats, and
move data, and answers the two questions the harness asks constantly: "how
effective is this move?" and "how hard does it hit?" Everything here is the
Gen 1 / Stadium ruleset — do not mix in later-gen mechanics.
"""
from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).parent

# Gen 1 splits physical vs special by TYPE, not per move.
SPECIAL_TYPES = frozenset({"fire", "water", "grass", "electric", "ice", "psychic", "dragon"})


def _load(name: str) -> dict:
    with open(_DIR / name, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_note", None)
    return data


class KB:
    def __init__(self) -> None:
        self.type_chart = _load("type_chart.json")
        self.base_stats = _load("base_stats.json")
        self.moves = _load("moves.json")
        self.dex_to_name = {v["dex"]: name for name, v in self.base_stats.items()}

    def effectiveness(self, atk_type: str, def_type: str) -> float:
        """Single-type multiplier (0 / 0.5 / 1 / 2). Missing pair == 1x."""
        return float(self.type_chart.get(atk_type.lower(), {}).get(def_type.lower(), 1.0))

    def type_multiplier(self, move_type: str, defender_types) -> float:
        """Full multiplier vs a (possibly dual-type) defender."""
        mult = 1.0
        for dt in defender_types:
            mult *= self.effectiveness(move_type, dt)
        return mult

    def category(self, move_type: str) -> str:
        return "special" if move_type.lower() in SPECIAL_TYPES else "physical"

    def species(self, name: str) -> dict:
        s = self.base_stats.get(name)
        if s is None:
            raise KeyError(f"unknown species: {name!r} (add it to kb/base_stats.json)")
        return s

    def move(self, name: str) -> dict:
        m = self.moves.get(name)
        if m is None:
            raise KeyError(f"unknown move: {name!r} (add it to kb/moves.json)")
        return m

    def name_for(self, dex: int) -> str:
        n = self.dex_to_name.get(dex)
        if n is None:
            raise KeyError(f"no species with dex #{dex} in the KB")
        return n


_default: KB | None = None


def default_kb() -> KB:
    global _default
    if _default is None:
        _default = KB()
    return _default
