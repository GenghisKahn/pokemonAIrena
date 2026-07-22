"""VisionBackend logic for the diamond turn model — decision detection (action bar vs
forced switch), reading BOTH actives off the panels (via the KB, so any of the 151 works),
peeking the move diamond, and committing via the diamond_select primitive. Fake OCR + fake
keyboard, no emulator/screen/engine."""
from __future__ import annotations

import yaml
from PIL import Image

from battle.observe import read_battle
from battle.state import Action
from kb import default_kb
from world.vision import VisionBackend


def _cfg():
    with open("config.yaml", encoding="utf-8") as f:
        c = yaml.safe_load(f)
    c["world"]["vision"].update({"menu_wait": 0, "turn_wait": 0, "poll": 0,
                                 "act_retries": 1, "end_polls": 2,
                                 "confirm_gap": 0, "confirm_polls": 2,
                                 "read_inventory": False})   # opt-in per inventory test
    return c


class _SeqOCR:
    """Canned text per recognize() call, in call order (repeats the last when spent)."""
    def __init__(self, texts):
        self._texts, self._i = list(texts), 0

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        t = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


class _FakeKeyboard:
    def __init__(self):
        self.presses = []
        self.selects = []           # diamond_select() directions

    def press(self, button, hold=0.0): self.presses.append(button)
    def hold(self, button, dur=0.0): self.presses.append(("hold", button))
    def _down(self, button): self.presses.append(("down", button))
    def _up(self, button): self.presses.append(("up", button))
    def diamond_select(self, direction, settle=0.0): self.selects.append(direction)
    def tap_sequence(self, buttons, gap=0.0): self.presses.append(list(buttons))
    def activate(self): self.presses.append("activate")


# snapshot() OCRs in this order: the action bar (switch_screen_open short-circuits on a
# move turn), then panels (self_name, self_hp, opp_name, opp_hp), then — after pressing
# "select" — a re-read of the bar to confirm it cleared (the press-retry check; "" = gone),
# then the move diamond (move_0..3).
_BAR = "A BATTLE B POKEMON S RUN"
_SNAP = [_BAR, "ODDISH", "125 / 125", "CLEFAIRY", "150 / 150",
         "",
         "Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def _backend(texts, kb=None):
    b = VisionBackend(_cfg(), ocr=_SeqOCR(texts), keyboard=kb or _FakeKeyboard())
    b._frame = lambda: Image.new("RGB", (16, 16))
    return b


def test_action_menu_detected():
    assert _backend([_BAR]).awaiting_input() is True
    assert _backend([""]).awaiting_input() is False


def test_forced_switch_detected():
    # Bar shows only "R Check" (no BATTLE / Cancel) after a faint -> a decision is needed.
    assert _backend(["R CHECK"]).awaiting_input() is True


def test_fainted_active_is_not_a_move_turn():
    # Action bar shows but our active reads fainted (hp 0) -> NOT a move turn (wait for the
    # forced-switch screen instead of trying to move / re-select the fainted mon).
    ocr = [_BAR, _BAR, "SQUIRTLE", "0 / 150", "MAGNEMITE", "105 / 105"]
    assert _backend(ocr).awaiting_input() is False
    # a live active on the same bar IS a move turn
    ocr_live = [_BAR, _BAR, "SQUIRTLE", "124 / 150", "MAGNEMITE", "105 / 105"]
    assert _backend(ocr_live).awaiting_input() is True


def test_forced_switch_excludes_the_fainted_active():
    kb = _FakeKeyboard()
    b = _backend([_BAR], kb=kb)
    b._self = {"dex": 35, "name": "Clefairy", "hp": 0, "max_hp": 176, "moves": []}
    b._opp = {"dex": 81, "name": "Magnemite", "hp": 26, "max_hp": 131, "moves": []}
    b._mon = lambda o, attr: None                              # keep the manual actives
    # party read even MISREADS the fainted Clefairy as alive; a live bench mon is present.
    b._peek_party = lambda: [{"name": "Clefairy", "hp": 176, "max_hp": 176},
                             {"name": "Sandshrew", "hp": 130, "max_hp": 156}]
    snap = b.snapshot()
    assert snap["awaiting"] == "switch"                        # fainted active -> forced switch
    hps = [p["hp"] for p in snap["self_party"]]
    assert hps[0] == 0 and hps[1] > 0                          # Clefairy forced fainted, Sandshrew live


def test_snapshot_reads_both_actives_from_the_screen():
    # Clefairy/Oddish aren't in config's teams — resolved purely via the KB (all 151).
    state = read_battle(_backend(_SNAP), default_kb(), level=50)
    assert state.self_active.name == "Oddish" and state.self_active.hp == 125
    assert state.opp_active.name == "Clefairy" and state.opp_active.hp == 150


def test_snapshot_reads_moves_from_diamond():
    state = read_battle(_backend(_SNAP), default_kb(), level=50)
    assert [state.self_active.moves[i].name for i in state.available_moves] == \
        ["Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def test_snapshot_peeks_moves_with_select_then_check():
    kb = _FakeKeyboard()
    _backend(_SNAP, kb=kb).snapshot()
    assert "select" in kb.presses                 # Z opens the pre-commit screen
    assert ("down", "check") in kb.presses        # Check held to reveal the diamond


def test_move_action_commits_via_diamond_select():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b.snapshot()                                  # populate actives + moves
    b.send_action(Action("move", 2))              # slot 2 -> down (index 2 in up,right,down,left)
    b.step()
    assert kb.selects[-1] == "down"


class _FixedOCR:
    """Every recognize() returns one fixed token — used to pin the bar/panel text."""
    def __init__(self, text): self.text = text

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        return [OCRResult(self.text, 0.9, (0.0, 0.0, 1.0, 1.0))]


def test_input_screen_open_true_on_menus_false_on_resolution():
    b = _backend([""])
    for bar in ("A BATTLE B POKEMON S RUN", "L CANCEL  R CHECK", "R CHECK"):
        b._ocr = _FixedOCR(bar)
        assert b._input_screen_open(b._frame()) is True     # still awaiting our input
    b._ocr = _FixedOCR("")
    assert b._input_screen_open(b._frame()) is False        # left the menus -> turn resolving


def test_await_commit_true_when_input_screen_clears_without_hp_change():
    # A status move / miss never moves HP; leaving the input screen is enough proof.
    b = _backend([""])
    b._ocr = _FixedOCR("")                                  # empty bar = resolving
    before = {"self": {"name": "Oddish", "hp": 50, "max_hp": 50},
              "opp": {"name": "Squirtle", "hp": 50, "max_hp": 50}}
    assert b._await_commit(before) is True


def test_await_commit_false_while_stuck_on_precommit_screen():
    # A dropped direction leaves us on the Cancel/Check screen; not committed -> retry.
    b = _backend([""])
    b._ocr = _FixedOCR("L CANCEL  R CHECK")
    before = {"self": {"name": "Oddish", "hp": 50, "max_hp": 50},
              "opp": {"name": "Squirtle", "hp": 50, "max_hp": 50}}
    assert b._await_commit(before) is False


class _PartyOCR:
    """Canned text per recognize() call, in order; returns '' once exhausted (so a
    trailing action_menu_open read resolves without repeating party text)."""
    def __init__(self, seq): self._seq, self._i = list(seq), 0

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        t = self._seq[self._i] if self._i < len(self._seq) else ""
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


def test_read_inventory_reads_bench_excluding_active_and_restores_menu():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b._self = {"dex": 104, "name": "Cubone", "hp": 0, "max_hp": 130, "moves": []}
    # read_party order per slot: name, then hp (slot_0, slot_1, slot_2).
    b._ocr = _PartyOCR(["CUBONE", "0 / 130", "MEOWTH", "120 / 120", "ODDISH", "125 / 125"])
    bench = b._read_inventory()
    assert [p["name"] for p in bench] == ["Meowth", "Oddish"]   # active (Cubone) dropped
    assert "pokemon" in kb.presses                              # opened the POKéMON screen
    assert ("down", "check") in kb.presses                      # revealed names+HP
    assert "activate" in kb.presses                             # focus grabbed (Windows-safe)


def test_read_inventory_is_failsafe_and_restores_menu_on_error():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b._self = {"dex": 104, "name": "Cubone", "hp": 0, "max_hp": 130, "moves": []}
    b._ocr = _PartyOCR([])                                      # empty reads -> not the menu
    import world.vision as _wv
    orig = _wv.read_party
    _wv.read_party = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ocr blew up"))
    try:
        assert b._read_inventory() == []                        # swallowed -> empty, no raise
    finally:
        _wv.read_party = orig
    assert kb.presses.count("cancel") >= 1                      # backed out to the action menu


def test_inventory_read_once_and_flows_to_switch_context():
    b = _backend(_SNAP)
    b.cfg["world"]["vision"]["read_inventory"] = True
    calls = []
    b._read_inventory = lambda: (calls.append(1),
                                 [{"dex": 52, "name": "Meowth", "hp": 120, "max_hp": 120}])[1]
    from battle.observe import read_battle
    state = read_battle(b, default_kb(), level=50)              # first move turn -> reads inventory
    b.snapshot()                                                # second -> does NOT re-read
    assert len(calls) == 1
    assert [p.name for p in state.party] == ["Meowth"]
    assert state.available_switches == (0,)                     # bench mon is switchable


def test_idle_step_advances_message_popups_off_menu():
    # No input screen up (empty bar = a message/animation frame) -> tap advance (Z).
    kb = _FakeKeyboard()
    b = _backend([""], kb=kb)
    b.pending = None
    b.step()
    assert "select" in kb.presses                          # dismissed the popup


def test_idle_step_does_not_advance_on_a_real_menu():
    # Action bar showing -> a real decision; must NOT press Z (would open the move diamond).
    kb = _FakeKeyboard()
    b = _backend([_BAR], kb=kb)
    b.pending = None
    b.step()
    assert "select" not in kb.presses


def test_battle_ends_after_leaving_the_battle_screens():
    # A settled non-battle screen (no bar, no panels) for end_polls checks -> battle over.
    b = _backend([""])                            # empty/result screen
    for _ in range(b.cfg["world"]["vision"]["end_polls"]):
        b.is_over()
    assert b.is_over() is True


class _PosOCR:
    """Returns a fixed set of positioned tokens (text, (x,y,w,h)) every recognize()."""
    def __init__(self, toks): self._toks = toks

    def recognize(self, _img):
        from vision.ocr import OCRResult
        return [OCRResult(t, 0.9, box) for t, box in self._toks]


def test_battle_result_wins_by_the_1p_row():
    from vision.observe import battle_result
    img = Image.new("RGB", (16, 16))
    # 1P (top) shares its row with LOSE, WIN is in COM's (bottom) row -> player lost.
    loss = _PosOCR([("1P", (0.12, 0.05, 0.10, 0.05)),
                    ("LOSE", (0.45, 0.22, 0.20, 0.06)),
                    ("WIN", (0.28, 0.71, 0.18, 0.06))])
    assert battle_result(img, loss) == "opponent"
    # flipped screen: WIN shares 1P's row -> player won.
    win = _PosOCR([("1P", (0.12, 0.05, 0.10, 0.05)),
                   ("WIN", (0.45, 0.22, 0.18, 0.06)),
                   ("LOSE", (0.28, 0.71, 0.20, 0.06))])
    assert battle_result(img, win) == "self"
    # no result screen.
    assert battle_result(img, _PosOCR([("A BATTLE", (0.4, 0.1, 0.2, 0.05))])) is None
