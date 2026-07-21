"""Prove the OCR pipeline end-to-end on a synthetic image — no emulator needed.

Renders text the way a battle screen would show it (a name and an HP fraction),
runs it through the real Vision engine, and checks we recover the strings. Skips
cleanly if the Vision bridge isn't installed.
"""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFont

pytest.importorskip("Vision")
from vision.ocr import VisionOCR  # noqa: E402


def _font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(lines: list[str]) -> Image.Image:
    img = Image.new("RGB", (640, 200), "white")
    d = ImageDraw.Draw(img)
    f = _font(56)
    y = 20
    for line in lines:
        d.text((30, y), line, fill="black", font=f)
        y += 80
    return img


def test_vision_reads_name_and_hp():
    ocr = VisionOCR()
    results = ocr.recognize(_render(["STARMIE", "166/166"]))
    text = " ".join(r.text for r in results).upper()
    assert "STARMIE" in text
    assert "166" in text


def test_results_have_boxes_and_confidence():
    ocr = VisionOCR()
    results = ocr.recognize(_render(["SNORLAX"]))
    assert results
    top = max(results, key=lambda r: r.confidence)
    assert 0.0 <= top.confidence <= 1.0
    x, y, w, h = top.bbox
    assert all(0.0 <= v <= 1.0 for v in (x, y, w, h))
