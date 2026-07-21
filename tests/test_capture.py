"""Capture backend selection + bbox conversion. We don't take a real screenshot here
(non-deterministic, needs a display) — we test the pure (x,y,w,h)->(l,t,r,b) mapping
and that capture_region dispatches to the right backend per platform / override."""
from __future__ import annotations

import sys

import pytest

from vision import capture


def test_ltrb_conversion():
    assert capture._ltrb(None) is None
    assert capture._ltrb((10, 20, 100, 50)) == (10, 20, 110, 70)   # x,y,w,h -> l,t,r,b


def test_unknown_backend_raises():
    with pytest.raises(ValueError) as exc:
        capture.capture_region(None, backend="mss")
    assert "mss" in str(exc.value)


def test_auto_dispatches_by_platform(monkeypatch):
    calls = []
    monkeypatch.setattr(capture, "_grab_screencapture", lambda b: calls.append(("sc", b)))
    monkeypatch.setattr(capture, "_grab_imagegrab", lambda b: calls.append(("ig", b)))
    capture.capture_region((0, 0, 10, 10), backend="auto")
    expected = "sc" if sys.platform == "darwin" else "ig"
    assert calls == [(expected, (0, 0, 10, 10))]


def test_explicit_backends_route(monkeypatch):
    calls = []
    monkeypatch.setattr(capture, "_grab_screencapture", lambda b: calls.append("sc"))
    monkeypatch.setattr(capture, "_grab_imagegrab", lambda b: calls.append("ig"))
    monkeypatch.setattr(capture, "_grab_window", lambda w: calls.append(("win", w)))
    capture.capture_region(None, "screencapture")
    capture.capture_region(None, "imagegrab")
    capture.capture_region(None, "window", window="RetroArch")
    assert calls == ["sc", "ig", ("win", "RetroArch")]


def test_pick_window_largest_match():
    infos = [
        {"kCGWindowOwnerName": "Finder", "kCGWindowNumber": 1,
         "kCGWindowBounds": {"Width": 800, "Height": 600}},
        {"kCGWindowOwnerName": "RetroArch", "kCGWindowNumber": 42,
         "kCGWindowBounds": {"Width": 640, "Height": 480}},      # small helper window
        {"kCGWindowOwnerName": "RetroArch", "kCGWindowNumber": 7,
         "kCGWindowBounds": {"Width": 1280, "Height": 960}},     # the main game window
    ]
    assert capture._pick_window(infos, "retroarch") == 7          # case-insensitive, largest
    assert capture._pick_window(infos, "Nonesuch") is None


def test_pick_window_matches_title_too():
    infos = [{"kCGWindowOwnerName": "python", "kCGWindowName": "RetroArch mupen64plus",
              "kCGWindowNumber": 9, "kCGWindowBounds": {"Width": 100, "Height": 100}}]
    assert capture._pick_window(infos, "retroarch") == 9
