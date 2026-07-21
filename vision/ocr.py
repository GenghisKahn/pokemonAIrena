"""OCR over the emulator screen — the vision path to battle state.

Backed by Apple's Vision framework (on-device, no Homebrew, strong on stylized
game fonts). recognize() takes a PIL image and returns text with normalized,
top-left-origin bounding boxes so callers can map results back to screen regions.

This is the observe layer for the "read the screen like a human" approach — no RAM
map required. It gives you what's printed (names, HP numbers); the KB supplies the
rest (types, base stats) from the recognized name.
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


def default_ocr():
    """Pick an available OCR engine (Vision on macOS). Raise with guidance if none."""
    try:
        return VisionOCR()
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "No OCR engine available. Install the macOS Vision bridge:\n"
            "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz\n"
            f"(import failed: {exc})"
        ) from exc
