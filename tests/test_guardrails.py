"""The gate must catch illegal and wasted moves and log why."""
from battle.observe import read_battle
from battle.state import Action
from guardrails import rules
from kb import default_kb
from world.mock import MockBattle

# Starmie's Thunderbolt is 0x into Rhydon (Ground/Rock) — a wasted turn.
_CFG = {
    "world": {"backend": "mock", "level": 50},
    "battle": {
        "player_team": [{"species": "Starmie", "moves": ["Thunderbolt", "Surf", "Blizzard", "Psychic"]}],
        "opponent_team": [{"species": "Rhydon", "moves": ["Earthquake", "Rock Slide"]}],
    },
    "guardrails": {"block_zero_effect": True, "warn_bad_switch": True},
}


def _state():
    kb = default_kb()
    backend = MockBattle(_CFG)
    return read_battle(backend, kb), kb


def test_zero_effect_move_is_replaced():
    state, kb = _state()
    tbolt = next(i for i, m in enumerate(state.self_active.moves) if m.name == "Thunderbolt")
    verdict = rules.check(state, Action("move", tbolt), kb, _CFG)
    assert not verdict.ok
    assert verdict.action.index != tbolt                      # substituted
    assert any("zero-effect" in v for v in verdict.violations)  # and logged


def test_legal_move_passes_clean():
    state, kb = _state()
    surf = next(i for i, m in enumerate(state.self_active.moves) if m.name == "Surf")
    verdict = rules.check(state, Action("move", surf), kb, _CFG)
    assert verdict.ok
    assert verdict.action == Action("move", surf)


def test_illegal_move_index_is_replaced():
    state, kb = _state()
    verdict = rules.check(state, Action("move", 99), kb, _CFG)
    assert not verdict.ok
    assert verdict.action.index in state.available_moves
    assert any("illegal-move" in v for v in verdict.violations)
