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

# Move DIAMOND cells, revealed by HOLDING Check (R/W) on the move pre-commit screen.
# Slot order matches world/vision.py::_SLOT_DIR = (up, right, down, left), so move_0=up,
# move_1=right, move_2=down, move_3=left. Live layout this session (Squirtle): ▲Up=SURF
# ◀Left=WITHDRAW ▶Right=ICE BEAM ▼Down=STRENGTH.
# ⚠️ APPROXIMATE — needs a live calibration pass against a real move-diamond viewport frame
# (see /tmp/pk_whold_view.png) with scripts/ocr_probe.py before reads are reliable.
MOVES: dict[str, tuple[float, float, float, float]] = {
    "move_0": (0.24, 0.10, 0.24, 0.06),   # up
    "move_1": (0.45, 0.16, 0.26, 0.06),   # right
    "move_2": (0.30, 0.22, 0.24, 0.06),   # down
    "move_3": (0.14, 0.16, 0.24, 0.06),   # left
}

# Party diamond on the forced-switch screen (revealed by HOLDING Check). A vertical list
# with a ▲/▶/▼ direction icon per entry; DIAMOND-SLOT order top->bottom = up, right, down.
# Boxes from the live check frame (/tmp/pk_checkheld.png). ⚠️ Calibrate live too.
PARTY: dict[str, tuple[float, float, float, float]] = {
    "slot_0_name": (0.28, 0.180, 0.30, 0.045), "slot_0_hp": (0.42, 0.200, 0.22, 0.045),  # up
    "slot_1_name": (0.28, 0.262, 0.30, 0.045), "slot_1_hp": (0.40, 0.330, 0.24, 0.045),  # right
    "slot_2_name": (0.28, 0.384, 0.30, 0.045), "slot_2_hp": (0.40, 0.452, 0.24, 0.045),  # down
}

# Action menu — the reliable turn start ("A BATTLE  B POKéMON  S RUN"), with both
# Pokémon panels visible. "bar" is the turn detector. self = the player's Pokémon = BLUE
# (top-left); opp = RED (bottom-right). HP boxes are widened on the left so a leading digit
# can't be clipped (avoids the 125->25 misread).
#
# Boxes are relative to the GAME VIEWPORT (4:3), which capture.py auto-crops out of the
# window (title bar + letterbox removed), so these are window-size-independent — no
# per-size re-tuning. Calibrated on a live 1476x1120 viewport (macOS). Re-probe against a
# cropped viewport frame (capture_region(...,'window')) only if the game's own HUD layout
# changes.
ACTION: dict[str, tuple[float, float, float, float]] = {
    "bar":       (0.35, 0.065, 0.52, 0.060),   # BATTLE / POKéMON / RUN bar
    "self_name": (0.04, 0.140, 0.28, 0.055),   # BLUE, top-left — the player's mon
    "self_hp":   (0.05, 0.255, 0.28, 0.045),
    "opp_name":  (0.70, 0.705, 0.28, 0.055),   # RED, bottom-right — the opponent
    "opp_hp":    (0.71, 0.820, 0.26, 0.045),
}
