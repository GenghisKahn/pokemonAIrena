# HANDOFF — pokemonAIrena (read this first)

_Last updated: 2026-07-22. Authoritative current-state briefing. Supersedes older notes in
`PROGRESS.md` / `state.md` where they conflict._

> ## 🪟 WINDOWS FORK (pokemonAIrena_kahn) — read this box first
>
> This is the **Windows** fork (origin github.com/GenghisKahn/pokemonAIrena). The body below is
> upstream's **macOS** briefing — the **game logic is shared** (turn model, the move DIAMOND, the
> non-standard RetroPad→N64 mapping), but the **OS plumbing differs**. On Windows:
> - **Capture:** `vision/capture.py::_grab_window_windows` — `PrintWindow(PW_CLIENTONLY |
>   PW_RENDERFULLCONTENT)`, occlusion-independent, Vulkan-OK, matched by window class `RetroArch`.
>   NOT `screencapture -l`. `_crop_to_viewport` runs on both OSes.
> - **Input:** `world/keyboard.py::WindowsKeyboard` — SendInput hardware scancodes. **No mouse-nudge
>   and no App-Nap workaround needed** (those are macOS-only); the 0.3s hold still applies. The
>   mouse-nudge/PostToPid parts of the input model below are macOS-specific — ignore them here.
>   Three Windows-input fixes were required (all in `WindowsKeyboard`): (1) the `INPUT` struct must
>   be 40 bytes — the union needs `MOUSEINPUT`, else `SendInput` returns 0 and sends nothing; (2)
>   `activate()` must force-focus via AttachThreadInput (plain SetForegroundWindow is refused for a
>   background process, so keys go to the wrong window); (3) this config binds A←`z` key, B←`a` key.
> - **OCR:** Tesseract with red-channel + 5x-upscale preprocessing and `word`/`number`/`line` modes
>   (`vision/ocr.py`); macOS uses Apple Vision. Both feed the same `observe`.
> - **Layout:** `vision/layout.py` splits `ACTION_WIN` / `ACTION_MAC` (opp panel differs by capture
>   trim), selected by platform.
>
> **✅ Live-verified on Windows:** observe end-to-end at the action menu (turn detection, both species
> Squirtle vs Meowth, HP), window-size- and aspect-independent (~1.319 viewport crop). 56 tests pass.
> **✅ MOVE SELECTION SOLVED (upstream's "ONE BLOCKER"):** the full commit works on Windows —
> `a` (A/BATTLE) → move-select screen → hold `r` (R/Check) renders the move diamond (▲SURF ◀WITHDRAW
> ▶ICE BEAM ▼STRENGTH + type/PP) → press the diamond direction (`dia_up`/`dia_left`/`dia_right`/
> `dia_down` = PgUp/Home/PgDn/End) to **select AND fire** the move. Proven: Surf → Meowth 120→50 →
> turn resolved → back at action menu. (Note: the "commit" is just pressing the C-diamond direction;
> no separate confirm key — upstream's blocker was really the broken SendInput struct + focus, above.)
> **Next on Windows:** wire this into `world/vision.py` — press A, hold R + OCR the diamond to read
> the 4 moves (calibrate `vision/layout.py::MOVES` to the diamond cells), map slot → `dia_*` in
> `_MOVE_KEYS`; then battle-end/faint detection for a full game.
> **Windows detail lives in `PROGRESS.md` (Windows port section).**

## Goal

An LLM/heuristic agent plays a **real Pokémon Stadium (Gen 1)** battle on RetroArch (macOS) by
**reading the screen (OCR) and driving the keyboard** — no RAM map. The harness owns the turn loop;
the agent proposes a move, a guardrail gate vets it, `send_input()` actuates it.

## Status at a glance

| Layer | State |
|---|---|
| Battle core (types, damage, KB, guardrails), mock backend, 57 tests | ✅ Done & passing |
| **Observe** (window capture → OCR → both panels + turn detection) | ✅ **Solid & window-size-independent** |
| Emulator config (windowed, no-pause, no crash-on-load) | ✅ Fixed & locked |
| **Input delivery** (reach the game, navigate, reach the move screen) | ✅ Cracked (flaky→reliable via mouse-nudge) |
| **Move commit** (actually USE a move) | ❌ **THE ONE BLOCKER** — sequence still unknown |
| Full turn end-to-end, then loop | ⛔ blocked on move commit |
| Faint/switch, battle-end detection, between-battle nav | ⛔ unbuilt (v1 only attacks) |

**Bottom line:** everything up to *selecting/committing a move* works. We can reliably observe both
Pokémon and drive the game to the move screen. We cannot yet make the Pokémon actually attack — the
exact key sequence that commits a move is the sole remaining unknown, and needs the user to demo it
(all guesses tested below failed).

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

## Verified in-battle flow (as far as it goes)

Action menu (`A BATTLE  B POKéMON  S RUN`, both panels visible) →
1. **`z`** (keycode 6, retry+nudge) → **cancel/check** screen (`L Cancel  R Check`). Reliable.
2. **Hold `w`** (keycode 13) → the **move DIAMOND** renders: **▲Up=SURF ◀Left=WITHDRAW ▶Right=ICE BEAM
   ▼Down=STRENGTH** (name+type+PP per cell). Frame: `/tmp/pk_whold_view.png`.
3. **??? — COMMIT A MOVE — UNKNOWN.** Tested and FAILED to fire a move: `L`, `x`/`a`/`s` (C-buttons),
   all four directions, and directions-while-holding-`w`. `L` just cancels back to the action menu.
   **Ask the user for the exact commit sequence** (e.g. "hold w, tap right, release" — but that
   specific one was tested and didn't fire). This is the single thing blocking a full turn.
   - Note: opp HP dropped 105→78 exactly once during a `z`-retry sequence — likely a fluke, unexplained.

`enter` (Start) also reaches a *different* cancel/check-like "look at field" screen; holding `w` there
shows NO diamond. **Use the `z` path, not `enter`.**

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

## Code changed this session (all UNCOMMITTED — `git status` shows them)

- `world/keyboard.py` — `MacKeyboard` now posts via `CGEventPostToPid` (resolves RetroArch pid,
  re-resolves if it restarts); `press()` default hold 0.05→0.3s. **Still needs: the mouse-nudge +
  retry logic folded in** (currently only in the `/tmp` scratch scripts).
- `vision/capture.py` — `_crop_to_viewport()` auto-crops window captures to the 4:3 game render area
  (drops title bar via "tallest non-black row band" + trims letterbox); wired into `_grab_window`.
  Makes layout boxes window-size-independent.
- `vision/layout.py` — `ACTION` boxes recalibrated to VIEWPORT coordinates (from full-window).
- `vision/observe.py` — `_HP` regex accepts whitespace separator (Apple Vision splits "105/105").
- `PROGRESS.md`, `state.md` — session notes.

Tests: **57 pass** after all changes (`python -m pytest -q`).

## Scratch artifacts (in `/tmp`, this session)

- `/tmp/pk_exp.py` — input+classify helpers (PostToPid press, save/reset, screen classify).
- `/tmp/pk_play_loop.py` — retry-until-HP-drops turn loop (move=`L`; landed 0 moves — needs the real
  commit key). `/tmp/pk_retryL.py` — retry-L probe.
- Frames: `/tmp/pk_whold_view.png` (the move diamond), `/tmp/pk_moveselect*.png`, `/tmp/pk_frame_window.png`.

---

## Immediate next steps (in order)

1. **Get the move-commit sequence from the user** (the blocker). Then wire it in and verify one full
   turn fires (opp HP drops) reliably with the nudge+retry pattern.
2. **Fold the working input pattern into `world/keyboard.py`** (mouse-nudge in `_down/_up`/`press`,
   and a retry-until-observed helper) and into `world/vision.py` (`snapshot()` / `_MOVE_KEYS` for the
   diamond: slot→direction or whatever the commit turns out to be).
3. **Calibrate `vision/layout.py::MOVES`** to the diamond cells and build `read_moves` for the diamond
   so the agent can pick the best move (not just one hardcoded button).
4. Loop turns (retry-until-effect) → then build **turn-completion + faint/switch + battle-end**
   detection for a full game.
5. Solve reliable **relaunch-into-battle** (menu "Run" activation) so crashes can auto-recover.

## What's solid and needs no rework

- Battle core / KB / guardrails / mock backend / 57 tests.
- Observe: `capture_region(...,'window')` → viewport crop → `action_menu_open` + `read_panels` reads
  both Pokémon (name+HP) at any window size. Verified across 1476×1120 and 1426×1081 viewports, 5/5.
