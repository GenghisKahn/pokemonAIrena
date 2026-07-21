"""OCR over the emulator screen — the vision path to battle state.

Two interchangeable engines behind one `recognize(img) -> list[OCRResult]` shape
(normalized, top-left-origin boxes):
  * VisionOCR   — Apple Vision framework (macOS only; on-device, strong on stylized
    game fonts, no external binary).
  * TesseractOCR — Tesseract via pytesseract (cross-platform: Windows/Linux/macOS).

`default_ocr(engine)` picks one: 'auto' uses Apple Vision on macOS and falls back to
Tesseract elsewhere; force with 'vision' or 'tesseract'. This is the observe layer
for the "read the screen like a human" approach — no RAM map required. It gives you
what's printed (names, HP numbers); the KB supplies the rest from the recognized name.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]   # (x, y, w, h), normalized, top-left origin


class VisionOCR:
    """Apple Vision VNRecognizeTextRequest. Language correction off (game text)."""

    def __init__(self) -> None:
        import Quartz
        import Vision
        from Foundation import NSData
        self._Quartz = Quartz
        self._Vision = Vision
        self._NSData = NSData

    def _cgimage(self, img: Image.Image):
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        raw = buf.getvalue()
        data = self._NSData.dataWithBytes_length_(raw, len(raw))
        src = self._Quartz.CGImageSourceCreateWithData(data, None)
        return self._Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    def recognize(self, img: Image.Image) -> list[OCRResult]:
        V = self._Vision
        cg = self._cgimage(img)
        req = V.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(False)
        handler = V.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, {})
        ok, _err = handler.performRequests_error_([req], None)
        if not ok:
            return []
        out: list[OCRResult] = []
        for obs in (req.results() or []):
            cand = obs.topCandidates_(1)
            if not cand:
                continue
            top = cand[0]
            r = obs.boundingBox()   # normalized, bottom-left origin
            x, y, w, h = r.origin.x, r.origin.y, r.size.width, r.size.height
            out.append(OCRResult(
                text=str(top.string()),
                confidence=float(top.confidence()),
                bbox=(x, 1.0 - y - h, w, h),   # flip to top-left origin
            ))
        return out


def _normalize_tesseract(data: dict, size: tuple[int, int]) -> list[OCRResult]:
    """pytesseract image_to_data (DICT) -> OCRResults with normalized top-left boxes.

    Tesseract confidence is 0-100 (or -1 for a non-text box); pixel coords are already
    top-left origin, so we just scale by the image size."""
    w, h = size
    out: list[OCRResult] = []
    for i in range(len(data["text"])):
        text = (data["text"][i] or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:          # conf == -1 marks a box with no text
            continue
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append(OCRResult(
            text=text,
            confidence=conf / 100.0,
            bbox=(x / w, y / h, bw / w, bh / h),
        ))
    return out


class TesseractOCR:
    """Tesseract via pytesseract — cross-platform (Windows / Linux / macOS).

    Needs the Tesseract binary on PATH plus `pip install pytesseract pillow`. `--psm 6`
    (assume a uniform block of text) suits the small region crops this harness OCRs."""

    def __init__(self, config: str = "--psm 6") -> None:
        import pytesseract
        self._pt = pytesseract
        self._config = config

    def recognize(self, img: Image.Image) -> list[OCRResult]:
        data = self._pt.image_to_data(
            img.convert("RGB"), config=self._config, output_type=self._pt.Output.DICT)
        return _normalize_tesseract(data, img.size)


_VISION_HELP = (
    "Apple Vision OCR unavailable (macOS only). Install the bridge:\n"
    "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
)
_TESSERACT_HELP = (
    "Tesseract OCR unavailable. Install the binary and the Python binding:\n"
    "  Windows: winget install UB-Mannheim.TesseractOCR   (or `choco install tesseract`)\n"
    "  macOS:   brew install tesseract\n"
    "  Linux:   apt-get install tesseract-ocr\n"
    "  then:    pip install pytesseract"
)


def default_ocr(engine: str = "auto"):
    """Pick an OCR engine. 'auto' = Apple Vision on macOS, Tesseract elsewhere; force
    with 'vision' or 'tesseract'. Raises with install guidance if the choice is unmet."""
    if engine not in ("auto", "vision", "tesseract"):
        raise ValueError(f"unknown OCR engine {engine!r} (expected 'auto', 'vision', or 'tesseract')")

    tried = []
    if engine in ("auto", "vision"):
        try:
            return VisionOCR()
        except Exception as exc:  # pragma: no cover - environment dependent
            if engine == "vision":
                raise RuntimeError(f"{_VISION_HELP}\n(import failed: {exc})") from exc
            tried.append(f"vision: {exc}")
    if engine in ("auto", "tesseract"):
        try:
            return TesseractOCR()
        except Exception as exc:  # pragma: no cover - environment dependent
            if engine == "tesseract":
                raise RuntimeError(f"{_TESSERACT_HELP}\n(import failed: {exc})") from exc
            tried.append(f"tesseract: {exc}")
    raise RuntimeError(
        "No OCR engine available.\n  " + "\n  ".join(tried)
        + f"\n\n{_VISION_HELP}\n\n{_TESSERACT_HELP}"
    )
