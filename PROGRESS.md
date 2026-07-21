# PROGRESS

## Done
- Scaffolded the harness (Pokémon-native layout, not mirroring flightgear).
- CLAUDE.md ported from flightgear_harness: behavioral rules verbatim; Project /
  What-Not-to-Touch / Success-Criteria rewritten for Pokémon Stadium (Gen 1).
- `kb/` — Gen 1 type chart (Stadium-corrected: Ghost→Psychic 2×), starter base-stats
  (17 species), move data. The load-bearing "meaning" layer.
- `battle/` — state types, `read_battle` (observe), `send_input` (act), Gen 1 stat +
  damage math.
- `guardrails/rules.py` — the gate: legality + quality (0× block, bad-switch warn),
  returns `Verdict{action, violations}`.
- `agent/player.py` — HeuristicPlayer (best-expected-damage, switches when stuck);
  LLMPlayer stub with heuristic fallback.
- `world/` — `Backend` protocol + factory; **mock** engine (deterministic 3v3, the
  default); project64 stub; retroarch stub with a **working UDP memory client**.
- `harness/loop.py` — the turn loop; `app.py` entry point.
- Tests: 18 pass (`pytest` or the manual runner). Default battle resolves to a
  winner deterministically. `python app.py` plays a full, sensible battle.
- Fixed an engine bug: a mon that fainted mid-turn had its just-switched-in
  replacement wrongly act with the fainted mon's move (actors now bind the
  attacker object at queue time).

## User-added (kept as-is)
- `tests/test_retroarch_transport.py` — validates the NCI client vs a fake UDP server.
- `scripts/probe_retroarch.py` — live probe for a running RetroArch + memory map.

## Vision path — "play it like a human" (alternative to RAM reading)
A second observe/act approach that needs no RAM map: read the screen, drive the keyboard.
- `vision/capture.py` — `capture_region()` (macOS `screencapture`) + `crop_norm()`.
- `vision/ocr.py` — `VisionOCR`, Apple Vision on-device OCR; normalized top-left boxes.
- `vision/layout.py` — `BATTLE` region boxes (**uncalibrated starting guesses**).
- `vision/observe.py` — `read_screen()` → self/opp name + self HP; KB fuzzy-matches the
  noisy OCR name to a real species (tolerates I↔l, 4↔A).
- `world/keyboard.py` — `press()/tap_sequence()` via Quartz CGEvent → RetroArch's default
  keyboard→RetroPad binds (X=A, Z=B, arrows=D-pad, Enter=Start). Needs Accessibility perm.
- `scripts/ocr_probe.py` — calibration tool: dump full-frame OCR + boxes, or show what each
  layout region reads, to line up `vision/layout.py` against a real Stadium frame.
- Deps live behind the `vision` extra (pillow + pyobjc Vision/Quartz). **Installed in this
  env; all 24 tests pass** including the two real-Apple-Vision OCR tests (`test_ocr.py`).

### Vision path — next
1. **Calibrate `vision/layout.py`** against a real Stadium battle frame (`ocr_probe.py
   --region ... --regions`). Needs the emulator running (user's machine).
2. **Extend `read_screen()`** past names+self-HP to the full struct: opp HP, the 4 moves +
   PP, status, and a menu-state read for turn detection.
3. **`VisionBackend` in `world/`** — stitch capture→observe (state) + keyboard (act) into the
   `Backend` protocol so `harness/loop.py` runs against live RetroArch, no RAM map.
4. **Turn detection from the screen** — the hard part; detect "awaiting move menu" from
   pixels/OCR rather than a menu byte.

## Next (build order)
- **Step 2 — RAM map.** Fill `world/retroarch.py::_ADDR` with the Stadium battle-struct
  addresses (self/opp species, HP, PP, status, stat stages, menu_state). Start from
  DataCrystal / TCRF; verify with `scripts/probe_retroarch.py` against a known HP.
  Then implement `snapshot()` to return the same shape as `MockBattle.snapshot()`.
- **Step 3 — turn detection + input.** `awaiting_input()` off the menu-state byte;
  `send_action()` via WRITE_CORE_MEMORY to the controller-poll address or a virtual gamepad.
- **Step 5 — LLMPlayer.** Prompt from BattleState, choose among available_moves/switches,
  fall back to HeuristicPlayer on any error.
- **Step 6 — arena + dashboard.** Win rate over N battles; reasoning/decision log UI.

## Notes / open questions
- base_stats.json is a 17-species subset; add the rest of the 151 as needed.
- Mock simplifications: no status/crit/accuracy rolls yet (deterministic max roll);
  voluntary switching supported, faint auto-switch picks first alive.
- Not a git repo yet.
