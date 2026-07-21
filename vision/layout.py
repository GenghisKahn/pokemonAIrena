"""Where the battle info sits on screen, as normalized (x, y, w, h) boxes.

These are STARTING GUESSES for a Pokemon Stadium battle (opponent top-left, your
Pokemon bottom-right). Calibrate them against a real frame with:

    python scripts/ocr_probe.py --out frame.png        # dump full-frame OCR + boxes

then nudge the numbers until each region reads the right text. Boxes are relative
to the captured region, so they're resolution-independent once the capture rect
matches the emulator viewport.
"""
from __future__ import annotations

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

# Action menu — the reliable turn start ("A BATTLE  B POKéMON  S RUN"), with both
# Pokémon panels visible. Calibrated from a live 1194x1228 RetroArch window (macOS,
# windowed). "bar" is the turn detector. self = the player's Pokémon = BLUE (top-left);
# opp = RED (bottom-right). HP boxes are widened on the left so a leading digit can't be
# clipped (avoids the 125->25 misread). Recalibrate with scripts/ocr_probe.py if aspect differs.
ACTION: dict[str, tuple[float, float, float, float]] = {
    "bar":       (0.34, 0.205, 0.52, 0.055),   # BATTLE / POKéMON / RUN bar
    "self_name": (0.06, 0.255, 0.26, 0.055),   # BLUE, top-left — the player's mon
    "self_hp":   (0.05, 0.340, 0.30, 0.045),
    "opp_name":  (0.70, 0.665, 0.26, 0.055),   # RED, bottom-right — the opponent
    "opp_hp":    (0.67, 0.748, 0.31, 0.045),
}
