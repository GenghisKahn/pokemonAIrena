"""Where the battle info sits on screen, as normalized (x, y, w, h) boxes.

These are STARTING GUESSES for a Pokemon Stadium battle (opponent top-left, your
Pokemon bottom-right). Calibrate them against a real frame with:

    python scripts/ocr_probe.py --out frame.png        # dump full-frame OCR + boxes

then nudge the numbers until each region reads the right text. Boxes are relative
to the captured region, so they're resolution-independent once the capture rect
matches the emulator viewport.
"""
from __future__ import annotations

import sys as _sys

# Normalized boxes, top-left origin, relative to the captured battle viewport.
BATTLE: dict[str, tuple[float, float, float, float]] = {
    "opp_name":  (0.05, 0.07, 0.36, 0.10),
    "opp_hp":    (0.05, 0.17, 0.32, 0.07),   # Stadium shows a bar; a number may not OCR
    "self_name": (0.59, 0.70, 0.36, 0.10),
    "self_hp":   (0.59, 0.80, 0.36, 0.08),   # your side usually shows numeric HP
}

# Move DIAMOND cells, revealed by HOLDING Check (R/W) on the move pre-commit screen.
# Slot order matches world/vision.py::_SLOT_DIR = (up, right, down, left), so move_0=up,
# move_1=right, move_2=down, move_3=left. The move NAME sits beside its direction arrow
# (▲ top / ◀ mid-left / ▶ mid-right / ▼ bottom). CALIBRATED live 2026-07-22 against
# Clefairy's diamond (▲DoubleSlap ▶Mega Punch ▼Thunder ◀Metronome) — cells read correctly.
# NB: reading a mon's real moves needs those moves in kb/moves.json (currently incomplete).
MOVES: dict[str, tuple[float, float, float, float]] = {
    "move_0": (0.35, 0.076, 0.25, 0.045),   # up    (name is left of the ▲ arrow, top row)
    "move_1": (0.65, 0.133, 0.26, 0.045),   # right (name is right of the ▶ arrow)
    "move_2": (0.62, 0.213, 0.27, 0.045),   # down  (name is right of the ▼ arrow, bottom row)
    "move_3": (0.32, 0.163, 0.25, 0.045),   # left  (name is left of the ◀ arrow)
}

# Party diamond on the forced-switch screen (revealed by HOLDING Check). A vertical list
# with a ▲/▶/▼ direction icon per entry; DIAMOND-SLOT order top->bottom = up, right, down.
# Boxes from the live check frame (/tmp/pk_checkheld.png). ⚠️ Calibrate live too.
PARTY: dict[str, tuple[float, float, float, float]] = {
    "slot_0_name": (0.30, 0.140, 0.29, 0.042), "slot_0_hp": (0.40, 0.198, 0.24, 0.048),  # up
    "slot_1_name": (0.30, 0.260, 0.29, 0.042), "slot_1_hp": (0.42, 0.325, 0.20, 0.045),  # right
    "slot_2_name": (0.30, 0.380, 0.29, 0.045), "slot_2_hp": (0.44, 0.450, 0.18, 0.042),  # down
}

# Action menu — the reliable turn start ("A BATTLE  B POKéMON  S RUN"), with both Pokémon
# panels visible. "bar" is the turn detector. self = the player's Pokémon = BLUE (top-left);
# opp = RED (bottom-right). HP boxes are widened on the left so a leading digit can't be
# clipped (avoids the 125->25 misread).
#
# Boxes are relative to the GAME VIEWPORT (4:3), which capture.py::_crop_to_viewport auto-crops
# out of the window (title bar + letterbox/pillarbox removed) on BOTH OSes. Verified: the crop
# holds a ~4:3 viewport (aspect ~1.319) across window sizes AND non-4:3 window shapes, so these
# ratios need no per-size re-tuning (assumes RetroArch renders 4:3, not stretched).
#
# `bar` + `self_*` are anchored to the viewport's top-left and read identically on both OSes.
# Only `opp_*` — anchored to the RIGHT/BOTTOM edge — lands at different ratios, because the
# Windows (PrintWindow, client-area) and macOS (screencapture -l, whole-window) crops trim
# those edges slightly differently. So opp_* is split per platform; the rest is shared.
_ACTION_SHARED: dict[str, tuple[float, float, float, float]] = {
    "bar":       (0.35, 0.065, 0.52, 0.060),   # BATTLE / POKéMON / RUN bar
    "self_name": (0.04, 0.140, 0.28, 0.055),   # BLUE, top-left — the player's mon
    "self_hp":   (0.05, 0.255, 0.28, 0.045),
}
ACTION_MAC: dict[str, tuple[float, float, float, float]] = {
    **_ACTION_SHARED,
    "opp_name":  (0.70, 0.705, 0.28, 0.055),   # RED, bottom-right — macOS (screencapture -l)
    "opp_hp":    (0.71, 0.820, 0.26, 0.045),
}
ACTION_WIN: dict[str, tuple[float, float, float, float]] = {
    **_ACTION_SHARED,
    "opp_name":  (0.752, 0.706, 0.175, 0.042),  # RED, bottom-right — Windows (PrintWindow), live-verified
    "opp_hp":    (0.75,  0.815, 0.20,  0.050),
}

ACTION: dict[str, tuple[float, float, float, float]] = (
    ACTION_WIN if _sys.platform == "win32" else ACTION_MAC
)

# The battle MESSAGE banner — the wide box across the BOTTOM ("MAGNEMITE used SUPERSONIC!",
# "X's DEFENSE rose!", "It's super effective!", "It became confused!", "Enough! Come back!").
# Used (best-effort) to surface turn EFFECTS into the agent's battle log. Live-calibrated
# 2026-07-22 against real message frames (text sits at y≈0.77, x≈0.14, spanning most of the
# width). ("Critical hit!" is a separate top-corner popup, not caught here.) A keyword filter
# keeps false positives low.
MESSAGE: tuple[float, float, float, float] = (0.13, 0.76, 0.74, 0.08)
