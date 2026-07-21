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

### VisionBackend (step 3) — DONE (unverified live)
- `world/vision.py::VisionBackend` — plays the REAL game with no RAM map. Key design: the
  static roster (species/movepools/PP/base stats) comes from `config.battle` (you don't OCR
  your own team); OCR tracks only the dynamic state (active mon by name→roster match, your
  HP, menu). Emits the same snapshot shape as mock, so `read_battle`/the loop are unchanged.
  Act via `world/keyboard.py` keystrokes; `_MOVE_KEYS`/`_switch_keys` are CALIBRATE points.
- `world/base.py` factory: `backend: vision`. `config.yaml world.vision{region, turn_wait}`.
- `tests/test_vision_backend.py` — 5 tests (fake OCR + fake keyboard, no emulator): roster
  from config, OCR→active+HP sync, snapshot feeds read_battle, move→keystroke map, bad-read
  keeps state. 34 tests pass.

### Vision path — move OCR + cross-platform (DONE)
- **Move-menu OCR** — `vision/observe.py`: `match_move` (fuzzy, space/case-tolerant),
  `read_moves` (4 slots → KB move names, skips empties), `menu_open` (lenient turn
  detector). VisionBackend now reads YOUR moves off the menu and resolves them via the
  KB — config moves are just a seed. `UnknownMoveError` fails loudly (names slot + raw
  text) when OCR reads a move not in `kb/moves.json`.
- **Cross-platform OCR** — `vision/ocr.py`: `TesseractOCR` (pytesseract, Win/Linux/mac)
  alongside `VisionOCR` (mac). `default_ocr(engine)`; `config world.vision.ocr` =
  auto|vision|tesseract. Deps split: `vision` extra now cross-platform, `vision-macos`
  holds pyobjc (platform-markered).
- **Cross-platform keyboard** — `world/keyboard.py`: `MacKeyboard` (Quartz) +
  `WindowsKeyboard` (SendInput scancodes, stdlib ctypes). `make_keyboard(driver)`;
  `config world.vision.keyboard` = auto|mac|windows.
- `requirements.txt` added (mirrors pyproject extras). 47 tests pass.
- NOTE: still unverified against a live emulator; regions + keystroke maps need calibration.

### Vision path — remaining (needs the emulator on the user's machine)
1. **Calibrate `vision/layout.py`** against a real Stadium frame (`ocr_probe.py --region
   ... --regions`) — the region boxes are still guesses.
2. **Calibrate keystroke maps** — verify `_MOVE_KEYS` (2×2 move grid) and `_switch_keys`
   against the actual Stadium menu flow + RetroArch binds; grant Accessibility permission.
3. **Refine turn detection** — `awaiting_input()` currently infers "in battle" from the
   active-name region; add a dedicated move-menu region once layout is calibrated.
4. **Opp HP / status** — OCR of the opponent's HP bar is unreliable; opp HP is tracked
   best-effort (starts full). The agent still gets the type matchup, the main signal.

## LLMPlayer (step 5) — DONE
- `agent/providers.py` — pluggable providers behind `complete(system, user) -> str`:
  `ClaudeProvider` (Anthropic SDK, default `claude-haiku-4-5`, SDK default credential
  resolution) and `LlamaCppProvider` (local `llama-server`, OpenAI-compatible
  `/v1/chat/completions`, stdlib urllib, no dep, no cost).
- `agent/player.py::LLMPlayer` — builds a compact BattleState prompt (legal moves with
  type/eff/est-dmg + legal switches), parses `move N` / `switch N`, validates against
  legal options, and falls back to HeuristicPlayer on any unparseable/illegal/error reply.
- `config.yaml` agent: `provider` (claude|llamacpp), `model`, `max_tokens`, `llamacpp{host,port}`.
- `tests/test_llm_player.py` — 5 tests (fake provider): valid pick used, prompt lists
  options, illegal/unparseable/provider-error all fall back to heuristic. 29 tests pass.
- CAVEAT: the Anthropic **API is metered per token** — a Claude Pro/Max *subscription*
  covers claude.ai + Claude Code, not raw Messages API calls. The zero-arg client uses
  whatever auth is configured (ANTHROPIC_API_KEY or an `ant auth login` OAuth profile).

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
