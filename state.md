# pokemonAIrena — Handoff State

_A cold-start briefing: what this is, how it fits together, what works, and what's next._

## What it is

An LLM agent plays **Pokémon Stadium (Gen 1)** battles on an N64 emulator. The
harness owns the turn loop — it reads the game's RAM to see the board, detects when
it's the agent's turn, vets the chosen move against a guardrail gate, and drives the
controller — with no human hands. The agent only ever *proposes*; the harness
observes, vets, and acts.

Full design rationale: `../pokemon-battle-harness-plan.md`. Project rules: `CLAUDE.md`.

## Quick start

```bash
python app.py            # play the default battle, one line per turn
python app.py --quiet    # just the final result
pytest                   # 18 tests: KB, damage, gate, full battle, RA transport
```

No emulator or ROM needed — the default backend (`world.backend: mock` in
`config.yaml`) is a deterministic in-memory Gen 1 engine. Everything is verifiable
today.

## Architecture (one turn)

`read_battle()` decodes the backend snapshot (dex IDs + raw numbers) → the
**knowledge base** turns it into meaning (types, base stats, effectiveness) → the
**player** proposes an `Action` → the **guardrail gate** vets it (illegal / 0× /
bad-switch), may substitute, and logs why → `send_input()` (the single door out)
actuates it → the backend resolves the turn. Loop until one side has no Pokémon.

```
world/       Backend protocol + factory; mock (default), project64, retroarch
kb/          type_chart · base_stats · moves  (Gen 1 / Stadium ruleset)
battle/      state types · read_battle (observe) · send_input (act) · damage math
guardrails/  the gate -> Verdict{action, violations}
agent/       HeuristicPlayer (baseline) + LLMPlayer (stub -> heuristic fallback)
harness/     the turn loop (loop.py)
app.py       entry point
scripts/     probe_retroarch.py (live NCI probe)
tests/       KB, damage, guardrails, full battle, retroarch transport
```

## Status

| Area | State |
|---|---|
| Knowledge base | ✅ type chart (Stadium-corrected), 17-species base stats, 18 moves |
| Damage/stat math | ✅ Gen 1 formula, single Special stat, category-by-type, deterministic |
| Observe / act | ✅ `read_battle` + `send_input` over the Backend protocol |
| Guardrail gate | ✅ legality + quality, logs every block |
| Players | ✅ HeuristicPlayer · ⬜ LLMPlayer (stub) |
| mock backend | ✅ deterministic 3v3, resolves to a winner |
| retroarch backend | ◑ UDP memory client works; RAM map + input TODO |
| project64 backend | ⬜ stub (needs JS-script bridge) |
| Tests | ✅ 18 passing (`pytest`) |

`python app.py` plays a full, sensible, deterministic battle (player wins the
default matchup in 8 turns, 0 gate blocks).

## Backends

| Backend | Platform | State read | Input | Status |
|---|---|---|---|---|
| `mock` | anywhere | in-memory engine | direct | working (dev/test default) |
| `retroarch` | macOS/Linux/Win | `READ_CORE_MEMORY` (UDP :55355) | RAM write / virtual gamepad | transport works; RAM map + input TODO |
| `project64` | Windows | `mem.u8` (script) | `joypad.set` | stub |

The RAM map and knowledge base are backend-independent — switching backends only
changes the observe/act plumbing, not battle logic.

## Gen 1 / Stadium rules encoded (do not mix in later gens)

- Single **Special** stat (no Sp.Atk/Sp.Def split); move **category is fixed by type**
  (special: fire/water/grass/electric/ice/psychic/dragon).
- **Ghost → Psychic is 2×** (RBY cartridge bug made it 0×; Stadium fixed it).
- Bug↔Poison mutually super-effective; Gen 1 immunities (Normal/Fighting→Ghost 0,
  Ground→Flying 0, Electric→Ground 0).
- Damage uses maxed DV/stat-exp at L50 with the classic RBY equation; deterministic
  max roll (no crit/accuracy/status rolls yet).

## Next steps (build order)

1. **RAM map (step 2)** — fill `world/retroarch.py::_ADDR` with the Stadium
   battle-struct addresses (self/opp species, HP, PP, status, stat stages,
   menu_state). Start from DataCrystal / TCRF; verify against a known HP using
   `scripts/probe_retroarch.py`. Implement `snapshot()` to match `MockBattle`'s shape.
2. **Turn detection + input (step 3)** — `awaiting_input()` off the menu-state byte;
   `send_action()` via WRITE_CORE_MEMORY to the controller-poll address or a virtual gamepad.
3. **LLMPlayer (step 5)** — prompt from BattleState, pick among available_moves/switches,
   fall back to HeuristicPlayer on any error.
4. **Arena + dashboard (step 6)** — win rate over N battles; reasoning/decision-log UI.

## Notes / open items

- `kb/base_stats.json` is a 17-species subset — add the rest of the 151 as needed.
- Mock simplifications: no status/crit/accuracy rolls; faint auto-switch picks first alive.
- User-added and kept as-is: `tests/test_retroarch_transport.py`, `scripts/probe_retroarch.py`.
- **Not a git repo yet** — no version control initialized.
- Fixed during build: a fainted mon's just-switched-in replacement was wrongly acting
  mid-turn (actors now bind the attacker object at queue time).
