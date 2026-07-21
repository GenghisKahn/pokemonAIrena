# pokemonAIrena

An LLM agent plays **Pokémon Stadium (Gen 1)** battles on an N64 emulator. The
harness owns the turn loop: it reads the game's RAM to see the board, detects when
it's the agent's turn, vets the chosen move, and drives the controller — no human
hands. See `pokemon-battle-harness-plan.md` (in the parent folder) for the full plan.

## Quick start

```bash
python app.py            # play the default battle, one line per turn
python app.py --quiet    # just the final result
pytest                   # verify the KB, damage math, gate, and a full battle
```

No emulator or ROM needed to run or test — the default backend is an in-memory
Gen 1 engine. Point at a real emulator by changing `world.backend` in `config.yaml`.

## How it fits together

```
world/  backends: mock (default), project64, retroarch      -> Backend protocol
kb/     type chart · base stats · moves  (Gen 1 / Stadium)   -> the meaning RAM lacks
battle/ state types · read_battle (observe) · send_input (act) · damage/matchup calc
guardrails/  the gate: legal + quality, returns Verdict{action, violations}
agent/  HeuristicPlayer (baseline) + LLMPlayer (stub, falls back to heuristic)
harness/  the turn loop: observe -> decide -> gate -> act -> step
```

One turn: `read_battle()` decodes the backend snapshot (dex IDs + numbers) and the
**knowledge base** turns it into meaning (types, stats, effectiveness). The player
proposes an `Action`; the **guardrail gate** vets it (illegal move, 0× waste, bad
switch) and may substitute, logging why; `send_input()` — the single door out —
actuates it; the backend resolves the turn.

## Backends

| Backend | Platform | State | Input | Status |
|---|---|---|---|---|
| `mock` | anywhere | in-memory engine | direct | **working** — the dev/test default |
| `retroarch` | macOS/Linux/Win | `READ_CORE_MEMORY` (UDP) | RAM write / virtual gamepad | UDP transport works; RAM map + input TODO |
| `project64` | Windows | `mem.u8` (script) | `joypad.set` | stub — needs the JS bridge |

## Build order (where we are)

1. ✅ Knowledge base + a deterministic engine so the whole loop runs and is tested.
2. ⬜ Map the Stadium battle struct in RAM (start from DataCrystal / TCRF).
3. ⬜ Turn detector + input loop against a real emulator.
4. ✅ Gate + heuristic player (done against the mock).
5. ⬜ LLM player (Claude picks the move; falls back to the heuristic).
6. ⬜ Arena (win rate over N battles) + reasoning dashboard.
