"""The KB is load-bearing — these lock the Gen 1 / Stadium ruleset in place."""
from kb import KB


def test_stadium_ghost_beats_psychic():
    # The headline Stadium fix: RBY had this as 0x (bug); Stadium made it 2x.
    assert KB().effectiveness("ghost", "psychic") == 2.0


def test_gen1_immunities():
    kb = KB()
    assert kb.effectiveness("normal", "ghost") == 0.0
    assert kb.effectiveness("fighting", "ghost") == 0.0
    assert kb.effectiveness("ground", "flying") == 0.0
    assert kb.effectiveness("electric", "ground") == 0.0


def test_gen1_specific_matchups():
    kb = KB()
    # Bug<->Poison were mutually super-effective in Gen 1 (changed later).
    assert kb.effectiveness("bug", "poison") == 2.0
    assert kb.effectiveness("poison", "bug") == 2.0
    assert kb.effectiveness("water", "fire") == 2.0
    assert kb.effectiveness("fire", "water") == 0.5


def test_dual_type_multiplier():
    kb = KB()
    # Rock/Ground doubly weak to Water.
    assert kb.type_multiplier("water", ("rock", "ground")) == 4.0
    # Ground does nothing to Electric/Flying (Flying immunity).
    assert kb.type_multiplier("ground", ("electric", "flying")) == 0.0


def test_category_is_by_type():
    kb = KB()
    assert kb.category("fire") == "special"
    assert kb.category("psychic") == "special"
    assert kb.category("normal") == "physical"
    assert kb.category("ground") == "physical"


def test_missing_pair_is_neutral():
    assert KB().effectiveness("normal", "water") == 1.0
