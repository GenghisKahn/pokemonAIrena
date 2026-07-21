"""Shared value types: the battle snapshot the agent sees, and the action it returns.

These are the whole surface the agent perceives — decoded from RAM (or the mock
engine) and enriched with the knowledge base. The agent proposes an Action; the
harness turns it into button presses.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MoveView:
    name: str
    type: str
    power: int
    category: str        # "physical" | "special" (derived from type)
    accuracy: int
    pp: int
    index: int           # slot 0-3 in the move menu


@dataclass(frozen=True)
class PokemonView:
    dex: int
    name: str
    types: tuple[str, ...]
    level: int
    hp: int
    max_hp: int
    status: str | None
    stages: dict = field(default_factory=dict)   # stat-stage boosts/drops
    stats: dict = field(default_factory=dict)     # computed Gen 1 stats: hp/atk/def/spc/spe
    moves: tuple[MoveView, ...] = ()              # populated only for your own active

    @property
    def hp_frac(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    @property
    def fainted(self) -> bool:
        return self.hp <= 0


@dataclass(frozen=True)
class BattleState:
    """One decoded turn — everything the agent needs to choose."""
    self_active: PokemonView
    opp_active: PokemonView
    party: tuple[PokemonView, ...]         # your bench (excludes the active mon)
    available_moves: tuple[int, ...]        # move slots with PP > 0
    available_switches: tuple[int, ...]     # party indices that aren't fainted
    awaiting: str | None                    # "move" | "switch" | None (nothing to decide)


@dataclass(frozen=True)
class Action:
    """What the agent proposes: use a move slot, or switch to a party index."""
    kind: str            # "move" | "switch"
    index: int
