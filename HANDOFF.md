# HANDOFF — pokemonAIrena (read this first)

_Last updated: 2026-07-22. Authoritative current-state briefing. Supersedes older notes in
`PROGRESS.md` / `state.md` where they conflict._

## Goal

An LLM/heuristic agent plays a **real Pokémon Stadium (Gen 1)** battle on RetroArch (macOS) by
**reading the screen (OCR) and driving the keyboard** — no RAM map. The harness owns the turn loop;
the agent proposes a move, a guardrail gate vets it, `send_input()` actuates it.

## Status at a glance

| Layer | State |
|---|---|
| Battle core (types, damage, KB, guardrails), mock backend, 58 tests | ✅ Done & passing |
| **Observe** (window capture → OCR → both panels + turn detection) | ✅ **Solid & window-size-independent** |
| Emulator config (windowed, no-pause, no crash-on-load) | ✅ Fixed & locked |
| **Input / move commit / switch** (`z` → C-button "diamond") | ✅ **SOLVED & live-verified** (move fired, switch worked) |
| **Harness wired for the diamond model** (keyboard + vision backend) | ✅ Implemented, 58 tests pass, imports clean |
| Live calibration of move/party diamond cells; end-to-end `app.py` | 🔧 needs one live pass |
| Battle-end detection / turn-completion tuning | 🔧 partial (`_changed` retry in; no win/loss screen yet) |

**Bottom line:** the whole turn is cracked and the harness is built around it. A full turn fires
(`z`→C-button committed Ice Beam; Squirtle fainted; a type-correct switch to Sandshrew worked). What
remains is a **live calibration/tuning pass**: dial in the `MOVES`/`PARTY` diamond-cell boxes against
real diamond frames, add win/loss detection, and run `python app.py` end-to-end.

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
- **`vision/observe.py`** — added `switch_screen_open` (faint detector) + `read_party`; `_HP` whitespace-tolerant.
- **`vision/layout.py`** — `ACTION` boxes at viewport coords; `MOVES` = diamond cells; new `PARTY` cells.
  ⚠️ `MOVES`/`PARTY` boxes are APPROXIMATE — need a live calibration pass.
- **`vision/capture.py`** — `_crop_to_viewport()` (title bar + letterbox removal) → window-size-independent.
- **`tests/test_vision_backend.py`** — rewritten for the diamond model.

Tests: **58 pass**; backend/player construct and all modules import clean. First commit of the earlier
half (`c26cf89`) is pushed; the diamond-model code above is the follow-up.

## Scratch artifacts (in `/tmp`, this session)

- `/tmp/pk_exp.py` — input+classify helpers (PostToPid press, save/reset, screen classify).
- `/tmp/pk_play_loop.py` — retry-until-HP-drops turn loop (move=`L`; landed 0 moves — needs the real
  commit key). `/tmp/pk_retryL.py` — retry-L probe.
- Frames: `/tmp/pk_whold_view.png` (the move diamond), `/tmp/pk_moveselect*.png`, `/tmp/pk_frame_window.png`.

---

## Immediate next steps (in order)

1. **Live-calibrate the diamond cell boxes.** Get a real move-diamond viewport frame (`z`→hold `w`) and
   a party frame, OCR them (`scripts/ocr_probe.py`), and set `vision/layout.py::MOVES` (up/right/down/left)
   and `PARTY` so `read_moves`/`read_party` read cleanly. The `MOVES`/`PARTY` boxes shipped are estimates.
2. **Run `python app.py` end-to-end** against a live battle at the action menu. Watch for: moves reading,
   the agent's pick, `diamond_select` firing, `_changed` confirming, and the forced-switch path. Tune
   `turn_wait` / `act_retries` / the peek timing.
3. **Battle-end detection** — `is_over()` currently returns `_done` (never set). Add a win/loss-screen
   detector (all 3 fainted / result screen) so a battle terminates instead of hitting `max_turns`.
4. Verify **switch peeking** (`read_party` slot→direction) matches the on-screen party order; confirm
   the fainted-active-in-slot-0 index model against `available_switches`.
5. Solve reliable **relaunch-into-battle** (menu "Run" activation) so crashes can auto-recover unattended.

**Live-session preamble every time:** launch RetroArch → History → Run the ROM → get to a battle action
menu → F2 (save state). Keep the RetroArch window a normal size (viewport crop handles the rest).

## What's solid and needs no rework

- Battle core / KB / guardrails / mock backend / 57 tests.
- Observe: `capture_region(...,'window')` → viewport crop → `action_menu_open` + `read_panels` reads
  both Pokémon (name+HP) at any window size. Verified across 1476×1120 and 1426×1081 viewports, 5/5.
