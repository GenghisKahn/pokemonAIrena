#!/usr/bin/env python3
"""Calibration tool for the vision path — capture the screen (or a rectangle),
run OCR, and print every string with its normalized box. Use it to line up the
regions in vision/layout.py against a real Pokemon Stadium battle.

    python scripts/ocr_probe.py                      # whole display
    python scripts/ocr_probe.py --region 100,80,960,720   # just the emulator viewport
    python scripts/ocr_probe.py --region ... --regions    # show what each layout box reads
    python scripts/ocr_probe.py --out frame.png           # also save the capture to eyeball

Needs the Vision bridge (pip install pyobjc-framework-Vision pyobjc-framework-Quartz).
"""
from __future__ import annotations

import argparse
import os
import sys

# Make the repo root importable when run as `python scripts/ocr_probe.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb import default_kb
from vision import layout as _layout
from vision.capture import capture_region, crop_norm
from vision.observe import read_screen
from vision.ocr import default_ocr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="x,y,w,h in screen points (default: whole display)")
    ap.add_argument("--regions", action="store_true", help="show what each layout box reads")
    ap.add_argument("--out", help="save the captured frame to this path")
    args = ap.parse_args()

    bbox = tuple(int(v) for v in args.region.split(",")) if args.region else None
    img = capture_region(bbox)
    if args.out:
        img.save(args.out)
        print(f"saved capture -> {args.out} ({img.size[0]}x{img.size[1]})\n")

    ocr = default_ocr()

    if args.regions:
        kb = default_kb()
        for name, box in _layout.BATTLE.items():
            text = " ".join(r.text for r in ocr.recognize(crop_norm(img, box)))
            print(f"  {name:<10} {box}  ->  {text!r}")
        print("\nparsed:", read_screen(img, ocr, kb))
        return 0

    results = sorted(ocr.recognize(img), key=lambda r: r.bbox[1])
    if not results:
        print("no text recognized. Is the battle on screen / capture rect right?")
        return 1
    print(f"{len(results)} text region(s):")
    for r in results:
        x, y, w, h = r.bbox
        print(f"  [{r.confidence:.2f}] ({x:.3f},{y:.3f},{w:.3f},{h:.3f})  {r.text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
