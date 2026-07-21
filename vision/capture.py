"""Screen capture for the vision path. Uses the built-in `screencapture` (no deps).

capture_region grabs a screen rectangle (points); crop_norm slices a normalized
box out of an already-captured frame. Capture once per turn, crop many regions.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from PIL import Image


def capture_region(bbox: tuple[int, int, int, int] | None = None) -> Image.Image:
    """Capture a screen rectangle (x, y, w, h) in points, or the whole display."""
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


def crop_norm(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop a normalized (x, y, w, h) box (top-left origin) out of img."""
    w, h = img.size
    x0, y0, bw, bh = box
    return img.crop((int(x0 * w), int(y0 * h), int((x0 + bw) * w), int((y0 + bh) * h)))
