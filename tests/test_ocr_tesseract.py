"""Tesseract OCR support: the pytesseract->OCRResult normalization (pure, needs no
binary) and default_ocr engine selection. The live Tesseract path is exercised only
where the binary is installed; here we lock the parts that are deterministic."""
from __future__ import annotations

import pytest

from vision.ocr import OCRResult, _normalize_tesseract, default_ocr


def test_normalize_tesseract_maps_boxes_and_conf():
    # Shape of pytesseract.image_to_data(output_type=DICT) over a 200x100 crop.
    data = {
        "text":   ["STARMIE", "", "166"],
        "conf":   [96.0, -1.0, 88.0],       # -1 == a non-text box, dropped
        "left":   [10, 0, 120],
        "top":    [20, 0, 20],
        "width":  [80, 0, 40],
        "height": [30, 0, 30],
    }
    out = _normalize_tesseract(data, (200, 100))
    assert [r.text for r in out] == ["STARMIE", "166"]     # blank/-1 conf dropped
    r = out[0]
    assert isinstance(r, OCRResult)
    assert r.confidence == pytest.approx(0.96)             # 0-100 -> 0-1
    assert r.bbox == pytest.approx((0.05, 0.20, 0.40, 0.30))  # pixels -> normalized top-left


def test_default_ocr_rejects_unknown_engine():
    with pytest.raises(ValueError) as exc:
        default_ocr("easyocr")
    assert "easyocr" in str(exc.value)


def test_default_ocr_tesseract_errors_helpfully_without_binding():
    # pytesseract isn't installed in this env; forcing 'tesseract' must raise with
    # install guidance rather than a bare ImportError.
    pytest.importorskip  # keep import local; no skip — we WANT the error path
    try:
        import pytesseract  # noqa: F401
    except Exception:
        with pytest.raises(RuntimeError) as exc:
            default_ocr("tesseract")
        assert "Tesseract" in str(exc.value) and "pip install pytesseract" in str(exc.value)
