"""Gen 1 stat + damage math."""
from battle.damage import battle_stats, gen1_stat
from kb import KB


def test_gen1_stat_values():
    # ((base+15)*2 + 63) * level//100, +5 for stats, +level+10 for HP, at L50.
    assert gen1_stat(100) == 151            # Tauros base Atk 100
    assert gen1_stat(160, is_hp=True) == 266  # Snorlax base HP 160


def test_battle_stats_shape():
    stats = battle_stats({"hp": 60, "atk": 75, "def": 85, "spc": 100, "spe": 115})
    assert set(stats) == {"hp", "atk", "def", "spc", "spe"}
    assert stats["spe"] > stats["atk"]      # Starmie is faster than it is strong


def test_super_effective_beats_neutral():
    kb = KB()

    class V:  # minimal PokemonView stand-in
        def __init__(self, types, stats):
            self.types, self.stats = types, stats

    from battle.damage import estimate_damage
    from battle.state import MoveView

    attacker = V(("water",), battle_stats({"hp": 79, "atk": 83, "def": 100, "spc": 85, "spe": 78}))
    rock = V(("rock", "ground"), battle_stats({"hp": 80, "atk": 110, "def": 130, "spc": 55, "spe": 45}))
    normal = V(("normal",), battle_stats({"hp": 75, "atk": 100, "def": 95, "spc": 70, "spe": 110}))
    surf = MoveView("Surf", "water", 95, "special", 100, 15, 0)

    assert estimate_damage(attacker, rock, surf, kb) > estimate_damage(attacker, normal, surf, kb)


def test_zero_effect_move_deals_nothing():
    kb = KB()
    from battle.damage import estimate_damage
    from battle.state import MoveView

    class V:
        def __init__(self, types, stats):
            self.types, self.stats = types, stats

    zapdos = V(("electric", "flying"), battle_stats({"hp": 90, "atk": 90, "def": 85, "spc": 125, "spe": 100}))
    rhydon = V(("ground", "rock"), battle_stats({"hp": 105, "atk": 130, "def": 120, "spc": 45, "spe": 40}))
    thunderbolt = MoveView("Thunderbolt", "electric", 95, "special", 100, 15, 0)

    assert estimate_damage(zapdos, rhydon, thunderbolt, kb) == 0  # Electric 0x vs Ground
