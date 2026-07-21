"""Screen capture for the vision path — cross-platform, three backends behind
capture_region():

  * screencapture — macOS built-in CLI, a screen rectangle (no dependency).
  * imagegrab     — Pillow ImageGrab (Windows + macOS; Pillow is already a vision dep).
  * window        — macOS: capture a specific window (e.g. RetroArch) BY IDENTITY, so
    it can be moved/resized freely and sit behind other windows in z-order. Because the
    game keeps a fixed aspect ratio, the normalized region boxes stay valid at any
    window size — no region rect to set or re-tune.

'auto' uses screencapture on macOS and ImageGrab elsewhere. Force via config
world.vision.capture. crop_norm slices a normalized box out of an already-captured
frame — capture once per turn, crop many regions.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageGrab


def _ltrb(bbox: tuple[int, int, int, int] | None):
    """(x, y, w, h) -> (left, top, right, bottom) for ImageGrab; None stays None."""
    if bbox is None:
        return None
    x, y, w, h = bbox
    return (x, y, x + w, y + h)


def _grab_screencapture(bbox: tuple[int, int, int, int] | None) -> Image.Image:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cmd = ["screencapture", "-x"]        # -x: silent
        if bbox is not None:
            cmd += ["-R", f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"]
        cmd.append(path)
        subprocess.run(cmd, check=True, capture_output=True)
        img = Image.open(path)
        img.load()
        return img
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _grab_imagegrab(bbox: tuple[int, int, int, int] | None) -> Image.Image:
    ltrb = _ltrb(bbox)
    img = ImageGrab.grab() if ltrb is None else ImageGrab.grab(bbox=ltrb)
    return img.convert("RGB")


def _pick_window(infos, match: str):
    """Largest on-screen window whose owner or title contains `match` (case-insensitive).
    `infos` is CGWindowListCopyWindowInfo output. Returns the CGWindowID, or None."""
    m = match.lower()
    best, best_area = None, -1
    for w in infos:
        owner = (w.get("kCGWindowOwnerName") or "")
        name = (w.get("kCGWindowName") or "")
        if m in owner.lower() or m in name.lower():
            b = w.get("kCGWindowBounds") or {}
            area = (b.get("Width") or 0) * (b.get("Height") or 0)
            if area > best_area:
                best_area, best = area, w.get("kCGWindowNumber")
    return best


def _find_window_id(match: str):
    import Quartz
    infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    return _pick_window(infos, match)


def _grab_window(match: str) -> Image.Image:
    """macOS: capture the window matching `match` by its CGWindowID (position/size/
    z-order independent). Needs Screen Recording permission and the window on-screen."""
    wid = _find_window_id(match)
    if wid is None:
        raise RuntimeError(
            f"No on-screen window matching {match!r} found. Is RetroArch running and "
            "visible (not minimized)? Set world.vision.window to match its title."
        )
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        # -l <id>: that window only; -o: no drop shadow; -x: silent.
        subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), path],
                       check=True, capture_output=True)
        img = Image.open(path)
        img.load()
        return img.convert("RGB")
    finally:
        if os.path.exists(path):
            os.unlink(path)


def capture_region(bbox: tuple[int, int, int, int] | None = None,
                   backend: str = "auto", window: str = "RetroArch") -> Image.Image:
    """Capture a screen rectangle, the whole display, or a specific window.

    backend:
      'auto'          — screencapture on macOS, ImageGrab elsewhere (uses bbox)
      'screencapture' — macOS rectangle capture (uses bbox)
      'imagegrab'     — Pillow ImageGrab (uses bbox)
      'window'        — macOS: capture the window whose title/owner contains `window`
                        (ignores bbox; move/resize-independent)
    """
    if backend == "auto":
        backend = "screencapture" if sys.platform == "darwin" else "imagegrab"
    if backend == "screencapture":
        return _grab_screencapture(bbox)
    if backend == "imagegrab":
        return _grab_imagegrab(bbox)
    if backend == "window":
        return _grab_window(window)
    raise ValueError(
        f"unknown capture backend {backend!r} "
        "(expected 'auto', 'screencapture', 'imagegrab', or 'window')"
    )


def crop_norm(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop a normalized (x, y, w, h) box (top-left origin) out of img."""
    w, h = img.size
    x0, y0, bw, bh = box
    return img.crop((int(x0 * w), int(y0 * h), int((x0 + bw) * w), int((y0 + bh) * h)))
