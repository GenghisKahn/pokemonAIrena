"""VisionBackend deterministic logic — roster, OCR->state sync, snapshot shape, and
action->keystroke mapping — with a fake OCR and fake keyboard, so no emulator, no
screen capture, and no OCR engine are touched.

What can't be verified headless (real capture, live calibration, turn timing) is
excluded here and flagged in world/vision.py; these tests lock the parts that CAN be
verified: the static roster, the read->update path, that the snapshot feeds
read_battle unchanged, and that an Action becomes the right keystrokes."""
from __future__ import annotations

import yaml
from PIL import Image

from battle.observe import read_battle
from battle.state import Action
from world.vision import VisionBackend


def _cfg():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class _FakeOCR:
    """read_screen calls recognize() 3x per read: self_hp, self_name, opp_name."""
    def __init__(self, self_hp, self_name, opp_name):
        self._texts = [self_hp, self_name, opp_name]
        self._i = 0

    def recognize(self, _img):
        from vision.ocr import OCRResult
        t = self._texts[self._i % len(self._texts)]
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


class _FakeKeyboard:
    def __init__(self):
        self.presses = []

    def tap_sequence(self, buttons, gap=0.0):
        self.presses.append(list(buttons))

    def press(self, button, hold=0.0):
        self.presses.append([button])


def _backend(self_hp="120 / 166", self_name="STARMIE", opp_name="SNORLAX", kb=None):
    # Avoid real screen capture: stub _frame so _sync_from_screen has an image to OCR.
    b = VisionBackend(_cfg(), ocr=_FakeOCR(self_hp, self_name, opp_name),
                      keyboard=kb or _FakeKeyboard())
    b._frame = lambda: Image.new("RGB", (16, 16))   # stub capture; fake OCR ignores content
    return b


def test_roster_built_from_config():
    b = _backend()
    # Player team from config.yaml: Starmie, Tauros, Exeggutor.
    names = [m.name for m in b.teams[0]]
    assert names == ["Starmie", "Tauros", "Exeggutor"]
    starmie = b.teams[0][0]
    assert starmie.max_hp > 0 and starmie.moves[0]["name"] == "Surf"


def test_sync_matches_active_and_updates_hp():
    # OCR says Tauros is out at 90/181 -> active index tracks Tauros, HP updates.
    b = _backend(self_hp="90 / 181", self_name="TAUROS", opp_name="RHYDON")
    b._sync_from_screen()
    assert b.teams[0][b.active[0]].name == "Tauros"
    assert b.teams[0][b.active[0]].hp == 90
    assert b.teams[1][b.active[1]].name == "Rhydon"


def test_snapshot_feeds_read_battle():
    from kb import default_kb
    b = _backend(self_hp="120 / 166", self_name="STARMIE", opp_name="SNORLAX")
    state = read_battle(b, default_kb(), level=50)
    assert state.self_active.name == "Starmie"
    assert state.self_active.hp == 120
    assert state.opp_active.name == "Snorlax"
    assert state.available_moves  # Starmie's moves are known from config, PP > 0


def test_move_action_maps_to_keystrokes():
    kb = _FakeKeyboard()
    b = _backend(kb=kb)
    b.cfg["world"]["vision"]["turn_wait"] = 0.0  # don't sleep in the test
    b.send_action(Action("move", 1))   # top-right slot
    b.step()
    assert kb.presses == [["right", "a"]]


def test_bad_read_keeps_last_state():
    # Empty name read must not crash or wipe the active pointer.
    b = _backend(self_hp="", self_name="", opp_name="")
    before = tuple(b.active)
    b._sync_from_screen()
    assert tuple(b.active) == before
