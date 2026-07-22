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

# Move-select menu: the four move names, in slot order (index 0-3 == send_input slot).
# STARTING GUESSES for Stadium's move list — calibrate with:
#   python scripts/ocr_probe.py --region ... --regions
# against the move-select screen (not the idle battle frame).
MOVES: dict[str, tuple[float, float, float, float]] = {
    "move_0": (0.08, 0.74, 0.40, 0.06),
    "move_1": (0.08, 0.80, 0.40, 0.06),
    "move_2": (0.08, 0.86, 0.40, 0.06),
    "move_3": (0.08, 0.92, 0.40, 0.06),
}

# Action menu — the reliable turn start ("A BATTLE  B POKéMON  S RUN"), with both Pokémon
# panels visible. "bar" is the turn detector. self = the player's Pokémon = BLUE (top-left);
# opp = RED (bottom-right).
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
