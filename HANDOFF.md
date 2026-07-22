# HANDOFF — pokemonAIrena (read this first)

_Last updated: 2026-07-22. Authoritative current-state briefing. Supersedes older notes in
`PROGRESS.md` / `state.md` where they conflict._

## Goal

An LLM/heuristic agent plays a **real Pokémon Stadium (Gen 1)** battle on RetroArch (macOS **and
Windows**) by **reading the screen (OCR) and driving the keyboard** — no RAM map. The harness owns the
turn loop; the agent proposes a move, a guardrail gate vets it, `send_input()` actuates it.

> **This branch (`combined_dev`) is the reconciliation of the macOS work (`brendan_dev`) with the merged
> Windows PR #1.** The GitHub PR merge into `master` accidentally clobbered the macOS input path — it
> reverted `_MAC_KEYCODES` to an unverified map (dropping the `c_*` C-buttons, so `diamond_select` raised
> `KeyError`), dropped the persistent mouse-mover thread, and left `vision/layout.py` referencing an
> undefined `_ACTION_SHARED`/`ACTION_MAC` (import error). This branch restores the live-verified macOS
> path, keeps the Windows additions, reconciles the Windows scancodes to PR #1's verified nav-key diamond,
> and unifies the docs. All **64 tests pass**. See "Windows support" below.

## Status at a glance

| Layer | State |
|---|---|
| Battle core (types, damage, guardrails), mock backend, **73 tests** | ✅ Done & passing |
| **Knowledge base** — 151 species base stats + **all 165 Gen 1 moves** | ✅ **Complete** (was 18 moves) |
| **Observe** (window capture → OCR → both panels + turn detection) | ✅ Solid & window-size-independent |
| Emulator config (windowed, no-pause, no crash-on-load) | ✅ Fixed & locked |
| **Input / move commit / switch** (`z` → C-button "diamond") | ✅ SOLVED & live-verified (macOS) |
| **Diamond cell calibration** (`MOVES` / `PARTY` boxes) | ✅ **Calibrated live** (reads real moves/party) |
| **Faint / switch flow** | ✅ Live-verified (auto-switched to a type-correct mon) |
| **Battle-end + winner detection** (`is_over` / `result`) | ✅ **Done & live-verified** on a real result screen |
| **`python app.py` driven by the *agent*, start to win/loss** | ✅ **DONE** — ran a full 9-turn battle autonomously (headless Claude CLI) |
| **Windows support** (capture · OCR · input) — merged from PR #1 | ◑ Observe + move-fire live-verified on Windows; not yet driven to a full game |

**Bottom line:** every mechanic is built, tested, and live-verified. An auto-player drove a **complete
battle** — Squirtle → (fainted) → Sandshrew → (fainted) → Clefairy, KO'd Oddish, lost to Psyduck's crit —
through faints, switches, and a detected loss screen. The KB is complete so the agent can classify any
moveset. **What remains is running `python app.py` so the *agent* (not the hardcoded auto-player) drives a
battle end to end, then tuning timings** (`turn_wait` / `act_retries` / peek cadence).

---

## The input model (macOS RetroArch, live-verified this session)

**Delivery:** synthetic keys via `CGEventPostToPid(<RetroArch pid>, ev)` — a *global* `CGEventPost`
does NOT reach RetroArch. Implemented in `world/keyboard.py` (`MacKeyboard`).

**Three reliability rules (all required, learned the hard way):**
1. **Long holds (~0.3s).** RetroArch polls core input per frame; a 50ms tap is missed. `press()`
   default hold is 0.3s.
2. **Mouse nudge after every key.** RetroArch throttles/doesn't render input unless the mouse moves.
   After each keydown/keyup, jiggle the cursor: `CGWarpMouseCursorPosition` + a `CGEventMouseMoved`
   to the window center. **This is what turned flaky input reliable.** (User's tip. Likely related to
   App Nap / run-loop throttling — App Nap is now disabled via `defaults`, but the nudge is still the
   proven fix; verify whether a *fresh* RetroArch launch removes the need for it.)
3. **Retry until the effect is observed.** Even with 1+2, some presses don't register. Retry the
   press and re-check the screen/HP until it changes. `z` often needs a few retries.

**The RetroPad→N64 mapping is NON-STANDARD** — do NOT trust `retroarch.cfg`'s `input_player1_*` names.
From RetroArch's *Port 1 Controls* menu (Settings→Input→Port 1 Controls), the live mapping is:
- key **x** → N64 **C1**, key **a** → **C2/B**, key **s** → **C4** (the face keys are **C-buttons**,
  which is why `x` (cfg calls it "N64 A") is a no-op at the action menu)
- key **q** → **L Shoulder**, key **w** → **R Shoulder (Check)**, key **enter** → **Start**
- N64 **A** (BATTLE) appears bound to *nothing useful on the keyboard* — no single key opened BATTLE.

## The turn primitive — "diamond select" (SOLVED, live-verified 2026-07-22)

Moves and switches are the SAME mechanic:
- **To READ options:** `z` (keycode 6) opens the pre-commit screen, then **HOLD `w`/Check** (kc13) to
  reveal the **diamond**: 4 move cells (▲Surf ◀Withdraw ▶Ice Beam ▼Strength) or, on a forced switch,
  the party (▲/▶/▼ = your Pokémon). *Holding `w` is for viewing only.*
- **To COMMIT:** `z` → the **C-button** for the direction. The four moves/party slots ARE the C-buttons:
  **▲Up=`n`(kc45) · ▼Down=`m`(kc46) · ◀Left=`b`(kc11) · ▶Right=`l`(kc37)**. (This is why "`L` used Ice
  Beam" — the user meant the **`l` key** = C-right = the ▶Ice Beam cell, not the L shoulder.)
- **Continuous mouse movement is mandatory** the whole time (see below). Retry until observe confirms.

Proven end-to-end: `z`→`l` fired Ice Beam (Magnemite took damage); Squirtle then fainted to Magnemite's
super-effective Electric; `z`→`m` sent out Sandshrew ("Go! SANDSHREW!"). `enter` (Start) reaches a
different "look at field" screen — ignore it; use the `z` path.

**Forced switch (faint):** same primitive. On a faint the bar shows only "R Check" (no BATTLE/Cancel).
HOLD `w` reveals the party as a diamond (▲/▶/▼ = your Pokémon; fainted ones show ✖/"FAINTED"), then
`z`→C-button picks one. `read_party` reads them in slot order and excludes fainted mons (their `0` HP
OCRs as the letter `O` — handled).

**Battle end + winner** (`vision/observe.py::battle_result`, live-verified): the result screen stacks
**`1P`** (player, top) over **`COM`** (opponent, bottom), each with a big **WIN**/**LOSE** word. The
WIN/LOSE nearest the `1P` row is the player's outcome → `"self"` (won) / `"opponent"` (lost). `is_over()`
checks this first, with a "left the battle screens for N polls" debounce as fallback.

---

## Emulator setup (macOS, App Store / sandboxed RetroArch 1.22.2)

- Config lives under the container, NOT `~/Library/Application Support`:
  `~/Library/Containers/com.libretro.dist.RetroArch/Data/Library/Application Support/RetroArch/config/retroarch.cfg`
- Core: **Mupen64Plus-Next** (`/Applications/RetroArch.app/Contents/Frameworks/mupen64plus.next.libretro.framework`).
- ROM: `Pokemon Stadium (USA) (Rev 2)/Pokemon Stadium (USA) (Rev 2).z64`.
- **Config changes made this session (locked so they persist):**
  - `video_fullscreen = "false"` (was reverting to true → windowed now)
  - `pause_nonactive = "false"` (don't pause when unfocused)
  - `input_joypad_driver = "hid"` (was `"mfi"` — the mfi driver **SIGSEGV'd in `input_joypad_analog_axis`
    on content load; that was the "History games won't load / crashes" bug)**
  - `config_save_on_exit = "false"` ← **this locks the above** so RetroArch stops overwriting them on exit.
    Trade-off: in-app setting changes no longer persist unless you edit the cfg. A `.bak-*` of the
    original cfg sits beside it.
  - App Nap disabled: `defaults write com.libretro.dist.RetroArch NSAppSleepDisabled -bool YES`
    (applies on next RetroArch launch).
- **Relaunch-into-a-battle recipe** (the sandboxed app ignores `--args` and a direct-binary exec fails):
  `open -a RetroArch` → goes to menu (No Core) → menu-nav to **History** tab → select the Pokémon
  Stadium entry (loads core+ROM) → **Run** → once the game renders, **F4** loads the save state back
  into the exact battle. ⚠️ Activating "Run" via synthetic input was unreliable — may need the user.
- **Save/restore a battle:** **F2** (kc120) saves state slot 0, **F4** (kc118) loads it. Both work
  reliably via PostToPid (function keys are reliable). State file:
  `.../Data/Documents/RetroArch/states/Mupen64Plus-Next/Pokemon Stadium (USA) (Rev 2).state`.
  **Make a save state at the action menu at the start of every live session** so experiments can reset.
- Menu navigation (if stuck in RetroArch's menu): arrows = kc123/124/125/126 move, `x`(kc7) = Back,
  **F1** (kc122) toggles the menu. Menu-OK/confirm-a-leaf ("Run") could NOT be reliably triggered.

---

## Code — the harness now implements the diamond model

- **`world/keyboard.py`** — `CGEventPostToPid` delivery; `press()` hold 0.3s; **added the C-button keys
  `n/m/b/l` + direction map (`_DIR_TO_C`); a persistent MOUSE-MOVER thread** (started in `MacKeyboard.__init__`,
  runs for the driver's life — the reliability fix); **`diamond_select(direction)`** (Z → C-button) and
  **`hold(button, dur)`** (Check). (One gotcha handled: pyobjc lazy imports aren't thread-safe — the Quartz
  symbols the mouse thread uses are force-resolved on the main thread first.)
- **`world/vision.py`** — rewritten for the diamond model: `awaiting_input` = action-bar OR forced-switch
  (inferred from prompts); `snapshot` reads panels, then peeks moves (`z`→hold `w`→OCR→cancel) or the party
  on a forced switch; `step` commits via `diamond_select(slot→direction)` with **retry-until-observed**
  (`_changed` checks HP/name moved). `_SLOT_DIR = (up,right,down,left)`.
- **`vision/observe.py`** — `switch_screen_open` (faint detector), `read_party` (fainted-aware),
  `on_battle_screen`, and **`battle_result`** (the WIN/LOSE result-screen reader); `_HP` tolerates
  `/`, whitespace, or `.` as the separator.
- **`vision/layout.py`** — `ACTION`, `MOVES` (move diamond), and `PARTY` boxes **all calibrated live**
  against real viewport frames.
- **`vision/capture.py`** — `_crop_to_viewport()` (title bar + letterbox removal) → window-size-independent.
- **`kb/moves.json`** — completed to **all 165 Gen 1 moves** (type/power/accuracy/pp; category derived
  from type; Gen-1 quirks encoded). `kb/base_stats.json` already had all 151 species.
- **`tests/test_vision_backend.py`** — diamond model + battle-end/`battle_result` tests.

Tests: **64 pass**; backend/player construct and all modules import clean.

## Windows support (merged from PR #1, reconciled here)

The vision path now runs on **Windows** too; `sys.platform` selects the OS-specific pieces and the shared
`observe`/harness logic is unchanged. What PR #1 added, and how it was reconciled onto the macOS work:

- **`vision/capture.py::_grab_window_windows`** — captures RetroArch's client area via `PrintWindow`
  (`PW_CLIENTONLY | PW_RENDERFULLCONTENT`): occlusion-independent, works with the **Vulkan** renderer,
  matched by window **class** (an Explorer folder named "RetroArch…" can't be grabbed). Stdlib `ctypes`.
  The shared `_crop_to_viewport` runs on both OSes (verified aspect ~1.319 across sizes/shapes).
- **`vision/ocr.py`** — a `TesseractOCR` backend (pytesseract) tuned for Stadium's font: red-channel
  isolation, 5× upscale, autocontrast; `recognize(mode=…)` (`word`/`number`/`line`). Apple Vision path
  unchanged; `config world.vision.ocr` = `auto|vision|tesseract`.
- **`vision/layout.py`** — `bar`/`self_*` are shared; `opp_*` is split `ACTION_MAC` vs `ACTION_WIN`
  (the two capture paths trim edges differently). `ACTION` picks by platform.
- **`world/keyboard.py::WindowsKeyboard`** — `SendInput` with hardware scancodes. Three live-fixed bugs:
  the `INPUT` struct must be 40 bytes (the union needs a `MOUSEINPUT` member or `SendInput` sends nothing);
  `activate()` force-focuses via `AttachThreadInput`; and the key binds were corrected.
- **Distinct input configs per OS (confirmed — they are two different RetroArch input maps, not one layout).**
  The shared `diamond_select` primitive is `press("select")` → settle → `press(_DIR_MAP[dir])`; each driver
  sets its own `_DIR_MAP`:
  - **macOS** (`MacKeyboard._DIR_MAP = _DIR_TO_C`) commits with the N64 **C-buttons** — `c_up/down/left/right`
    = N/M/B/L keys.
  - **Windows** (`WindowsKeyboard._DIR_MAP = _DIR_TO_DIA`) commits with the **PgUp/Home/PgDn/End nav cluster**
    — `dia_up/left/right/down` (live-verified in PR #1).
  Only the open/preview/back keys coincide (both configs put `select`/`check`/`cancel` on Z/W/Q), so those
  keep shared names; the diamond commit is fully separate per OS. Neither map borrows the other's key names.

## Team inventory read at battle start (both OSes)

So the agent has bench context for type matchups and voluntary switches from turn 1 (not only when a
faint forces a switch), `VisionBackend` reads the full roster once at the first move turn:
`world/vision.py::_read_inventory()` opens the **POKéMON** action-bar screen (`pokemon` keymap button),
reveals names+HP (hold Check → `read_party`), drops the active mon, and stores the switchable bench —
then backs out to the action bar. It's **fail-safe**: any trouble returns `[]` and `_restore_action_menu()`
cancels back so the turn loop never strands on a sub-menu. Enabled via `world.vision.read_inventory: true`.

OS-agnostic by construction (it goes through the keyboard/OCR interfaces); the only per-OS bit is the
`pokemon` keycode (`_MAC_KEYCODES`/`_WIN_SCANCODES`, override via `world.vision.pokemon_button`).
⚠️ **Two things need one live pass per platform:** (1) the `pokemon` keycode is a best guess (macOS: key
`a`→N64 B; Windows: `0x1E`) — verify it actually opens POKéMON; (2) the party OCR reuses the forced-switch
`PARTY` boxes, still macOS-calibrated, so the diamond cells want a Windows-crop calibration. Logic is unit-
tested (bench excludes active; fail-safe restores the menu; read happens once and flows to `available_switches`).

## Autonomous run — `python app.py` (done, headless CLI)

`app.py` ran a **complete 9-turn battle on its own** — the harness observed, decided, and acted with no
per-turn human input; every move was chosen by Claude via the **`claudecli`** provider. Loop per turn
(`harness/loop.py`): `awaiting_input()` → `read_battle()` (OCR + KB) → `player.decide()` → gate → `send_input`
→ `step()` → repeat until `is_over()`. Result correctly detected (`winner: opponent`, matching the on-screen
LOSE screen). The agent's **moves and types are the decision context** — `LLMPlayer._prompt` feeds each legal
move's type, power, effectiveness-vs-opponent, and estimated damage, plus both actives' types.

**Providers (`agent/providers.py`, pick via `agent.provider`):** `claude` (Anthropic API, needs a key) ·
`llamacpp` (local `llama-server`) · **`claudecli`** (shells to `claude -p` — your Claude subscription, no
key, no server; the way to test the loop on a machine running Claude Code). Config default is `claudecli`.

**Live-loop robustness (found running it for real; unit tests don't exercise timing):**
- **`is_over()` false-end fix** — a normal move ANIMATION hides the panels/bar, so the old `end_polls=5`
  debounce mistook it for battle-over (quit after 1 turn). `battle_result` (WIN/LOSE screen) is the real
  end signal; the debounce backstop is now `end_polls=40`.
- **`eager_keyboard`** — `reset()` brings the keyboard (mouse-mover) up immediately, so a live game can't
  stall before the first action menu (RetroArch idle-throttle).
- **`advance_popups`** — while idle, `_advance_popups()` taps **Z** to dismiss blocking message boxes
  ("X fainted!" / "Go! Y!" / "no will to fight") so the loop reaches the next decision instead of getting
  **stuck on a faint popup** before the forced-switch screen. GUARDED by `_input_screen_open()` — it never
  presses Z when the action bar / pre-commit / forced-switch screen is up (there Z would open the diamond).
  All three are `world.vision.*` config knobs.

## Cross-platform (macOS + Windows) status of the loop features

The whole loop + all three robustness features go through the keyboard/OCR interfaces, so they are
**OS-agnostic by construction** and run on Windows too. Per-OS specifics and what still needs a live pass:
- **`advance_popups` / `eager_keyboard` / `is_over`** — logic identical on both; the only OS difference is
  input delivery (macOS `CGEventPostToPid` + a persistent mouse-mover; Windows `SendInput`). The mouse-mover
  is macOS-only (it fixes RetroArch's idle-throttle there); on Windows `SendInput` doesn't need it, but
  whether Windows RetroArch keeps rendering during idle polls is **unverified** — if it throttles, the
  Windows path needs its own nudge. `advance_button`/`pokemon_button` use shared keymap names resolved
  per-OS.
- **Windows still-unverified end-to-end:** `diamond_select`/peek through the harness, the `MOVES`/`PARTY`/
  inventory OCR on the PrintWindow crop (macOS-calibrated), faint-switch, and `battle_result`. And on
  Windows, `SendInput` needs the window focused — `activate()` is called at keyboard creation and before
  the inventory read, but a per-act re-`activate()` may be needed if focus drifts (see Windows-support gaps).

## Scratch artifacts (in `/tmp`)

- `/tmp/pk_drive.py` — persistent-mouse harness (the reliable input pattern). `/tmp/pk_conclude.py` — the
  auto-player that drove a full battle to its end. Helpers: `/tmp/pk_exp.py`.
- Frames: `/tmp/pk_movediamond2.png` (Clefairy move diamond), `/tmp/pk_checkheld.png` (party check),
  `/tmp/pk_RESULT.png` (the 1P=LOSE / COM=WIN result screen).

---

## Immediate next steps (in order)

1. **Run `python app.py` agent-driven, end to end.** The mechanics are proven by the auto-player; the
   remaining step is letting the *agent* (`config.yaml` → `agent.player: heuristic` for no-API, or `llm`)
   drive: observe → decide → `diamond_select` → confirm → loop through faints/switches → detected win/loss.
   Watch the forced-switch path and `_changed` confirmation; tune `turn_wait` / `act_retries` / peek cadence.
2. **Reliability polish:** the input is reliable-*ish* with the persistent mouse-mover + retry, but expect
   occasional missed presses — the retry-until-observed loop absorbs them; widen retries/waits if needed.
3. Solve reliable **relaunch-into-battle** (menu "Run" activation) so a core crash can auto-recover unattended
   (currently needs the user to click Run; then `F4` loads the save state).
4. Pre-battle menu navigation (choosing mode/cup/team) is still unbuilt — a fresh battle is set up manually.

**Live-session preamble every time:** launch RetroArch → History → Run the ROM → get to a battle action
menu → **F2** (save state) so experiments can reset. Keep the RetroArch window a normal size (the viewport
crop handles sizing).

## What's solid and needs no rework

- Battle core / KB (165 moves + 151 species) / guardrails / mock backend / 64 tests.
- Observe: `capture_region(...,'window')` → viewport crop → `action_menu_open` + `read_panels` reads both
  Pokémon (name+HP) at any window size. Verified across multiple viewport sizes.
- The full act path: `diamond_select` (moves + switches), continuous mouse, retry-until-observed, faint
  handling, and battle-end/winner detection — all live-verified in a complete battle.
