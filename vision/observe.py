"""read_screen() — the vision observe. Turn a captured battle frame into the main
components: who's out and your HP. OCR reads the pixels; the KB resolves the noisy
name string to a real species (and, downstream, its types and base stats).

This is the OCR-first milestone: names + HP now, the full battle struct later.
"""
from __future__ import annotations

import re
from difflib import get_close_matches

from kb import KB
from vision import layout as _layout
from vision.capture import crop_norm

_HP = re.compile(r"(\d+)\s*[/il|]\s*(\d+)")   # tolerate OCR misreads of '/'

_MOVE_SLOTS = ("move_0", "move_1", "move_2", "move_3")


class UnknownMoveError(LookupError):
    """OCR read a move name in the menu that no KB entry matches — the KB is
    incomplete (or the move-slot region is misaligned). The message names the slot
    and the raw text so it's actionable."""


def _region_text(img, ocr, box) -> str:
    return " ".join(r.text for r in ocr.recognize(crop_norm(img, box))).strip()


def match_species(text: str, kb: KB) -> str | None:
    """Fuzzy-match an OCR'd name to a KB species (handles case + a few wrong letters)."""
    token = re.sub(r"[^A-Za-z]", "", text or "").title()
    if not token:
        return None
    hits = get_close_matches(token, list(kb.base_stats.keys()), n=1, cutoff=0.6)
    return hits[0] if hits else None


def match_move(text: str, kb: KB) -> str | None:
    """Fuzzy-match an OCR'd move label to a KB move key (case- and space-tolerant).

    Move names have spaces/hyphens (`Hyper Beam`, `Double-Edge`), so unlike species
    we keep separators and compare lowercased. Returns None if nothing is close."""
    token = re.sub(r"\s+", " ", (text or "").strip())
    if not token:
        return None
    keys_lower = {k.lower(): k for k in kb.moves}
    if token.lower() in keys_lower:
        return keys_lower[token.lower()]
    hits = get_close_matches(token.lower(), list(keys_lower), n=1, cutoff=0.6)
    return keys_lower[hits[0]] if hits else None


def read_moves(img, ocr, kb: KB, regions: dict | None = None) -> list[str]:
    """OCR the move-select menu -> KB move names, in slot order.

    Empty slots (a mon with <4 moves) are skipped. A slot with text that matches no
    KB move raises UnknownMoveError — fail loudly, because a mis-identified move makes
    every downstream decision (and keystroke) wrong."""
    R = regions or _layout.MOVES
    names: list[str] = []
    for slot in _MOVE_SLOTS:
        raw = _region_text(img, ocr, R[slot])
        if not raw.strip():
            continue
        matched = match_move(raw, kb)
        if matched is None:
            raise UnknownMoveError(
                f"Move OCR read {raw!r} in {slot}, but no move in kb/moves.json "
                f"matches it. Add the move (name, type, power, accuracy, pp) to "
                f"kb/moves.json, or fix the {slot} box in vision/layout.py."
            )
        names.append(matched)
    return names


def menu_open(img, ocr, kb: KB, regions: dict | None = None) -> bool:
    """Lenient turn detector: True if any move slot resolves to a KB move. Never
    raises (unlike read_moves) — used to decide *whether* the move menu is up."""
    R = regions or _layout.MOVES
    return any(match_move(_region_text(img, ocr, R[slot]), kb) for slot in _MOVE_SLOTS)


def read_screen(img, ocr, kb: KB, regions: dict | None = None) -> dict:
    R = regions or _layout.BATTLE
    self_hp = _HP.search(_region_text(img, ocr, R["self_hp"]))
    return {
        "self": {
            "name": match_species(_region_text(img, ocr, R["self_name"]), kb),
            "hp": int(self_hp.group(1)) if self_hp else None,
            "max_hp": int(self_hp.group(2)) if self_hp else None,
        },
        "opp": {
            "name": match_species(_region_text(img, ocr, R["opp_name"]), kb),
        },
    }
