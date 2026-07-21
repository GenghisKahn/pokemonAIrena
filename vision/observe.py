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


def _region_text(img, ocr, box) -> str:
    return " ".join(r.text for r in ocr.recognize(crop_norm(img, box))).strip()


def match_species(text: str, kb: KB) -> str | None:
    """Fuzzy-match an OCR'd name to a KB species (handles case + a few wrong letters)."""
    token = re.sub(r"[^A-Za-z]", "", text or "").title()
    if not token:
        return None
    hits = get_close_matches(token, list(kb.base_stats.keys()), n=1, cutoff=0.6)
    return hits[0] if hits else None


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
