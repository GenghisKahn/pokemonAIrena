"""vision — a Backend that plays the REAL Pokemon Stadium on RetroArch, no RAM map.

Turn model (what a human sees each turn):
  1. The ACTION menu appears — "A BATTLE  B POKéMON  S RUN" — with both Pokémon panels
     (species + HP) visible. This is the reliable turn start.
  2. To attack: press A (BATTLE), the move list opens, pick a move, confirm.

So each turn the harness: detects the action menu (awaiting_input), reads BOTH actives
off the panels, presses A to open the moves, reads them (resolved via the KB), the agent
picks, and the keystrokes navigate the open move menu. Because the KB knows all 151, it
reads whoever is on screen — no team setup in config.yaml needed.

State (observe) comes from `vision/` (window capture + OCR); actions (act) go out through
`world/keyboard.py`. read_battle() sees the same snapshot shape as the mock.

⚠️ CALIBRATE before a live run (not verifiable headless):
  * ACTION regions in vision/layout.py are calibrated to a 1194x1228 window; MOVES are
    still guesses — align them from a move-select frame (scripts/ocr_probe.py).
  * _MOVE_KEYS below assumes the move menu's layout; verify against the real menu.
  * Grant Screen Recording (capture) + Accessibility (keystrokes) to your terminal.
"""
from __future__ import annotations

import time

from battle.damage import battle_stats
from battle.state import Action
from kb import default_kb
from vision import layout as _layout
from vision.capture import capture_region
from vision.observe import action_menu_open, read_moves, read_panels

# Move menu navigation, from the menu already opened by pressing A. Cursor starts on
# slot 0; the trailing "a" confirms. CALIBRATE to Stadium's actual move layout.
_MOVE_KEYS = {
    0: ["a"],
    1: ["down", "a"],
    2: ["down", "down", "a"],
    3: ["down", "down", "down", "a"],
}


class VisionBackend:
    """Observe Stadium via OCR (window capture), act via the keyboard. Reads whoever
    is on screen through the KB — no config roster required."""

    def __init__(self, cfg: dict, ocr=None, keyboard=None):
        self.cfg = cfg
        self.kb = default_kb()
        self.level = cfg["world"].get("level", 50)
        v = cfg["world"].get("vision", {})
        self.region = tuple(v["region"]) if v.get("region") else None
        self._ocr = ocr
        self._kb_input = keyboard
        self.reset()

    def reset(self) -> None:
        self._self = None   # {dex, name, max_hp, hp, moves:[{name,pp,type}]}
        self._opp = None
        self.pending: Action | None = None
        self._done = False

    # ---- dependencies (lazy on real runs) ----------------------------------
    def _ocr_engine(self):
        if self._ocr is None:
            from vision.ocr import default_ocr
            self._ocr = default_ocr(self.cfg["world"].get("vision", {}).get("ocr", "auto"))
        return self._ocr

    def _keyboard(self):
        if self._kb_input is None:
            from world.keyboard import make_keyboard
            kb = make_keyboard(self.cfg["world"].get("vision", {}).get("keyboard", "auto"))
            kb.activate()
            self._kb_input = kb
        return self._kb_input

    def _frame(self):
        v = self.cfg["world"].get("vision", {})
        return capture_region(self.region, v.get("capture", "auto"), v.get("window", "RetroArch"))

    # ---- observe -----------------------------------------------------------
    def awaiting_input(self) -> bool:
        if self._done:
            return False
        return action_menu_open(self._frame(), self._ocr_engine(), self.kb, _layout.ACTION)

    def _update_active(self, attr: str, o: dict) -> None:
        """Build/refresh a cached active from an OCR'd {name, hp, max_hp} via the KB.
        A missed name keeps the last-known mon (only HP updates); a resolved name that
        matches the current mon preserves its already-read moves."""
        cur = getattr(self, attr)
        name = o.get("name")
        if name:
            sp = self.kb.species(name)
            max_hp = battle_stats(sp["base"], self.level)["hp"]
            same = cur is not None and cur["name"] == name
            hp = o["hp"] if o.get("hp") is not None else (cur["hp"] if same else max_hp)
            setattr(self, attr, {
                "dex": sp["dex"], "name": name, "max_hp": max_hp,
                "hp": max(0, min(max_hp, hp)),
                "moves": cur["moves"] if same else [],
            })
        elif cur is not None and o.get("hp") is not None:
            cur["hp"] = max(0, min(cur["max_hp"], o["hp"]))

    def _move_entry(self, name: str) -> dict:
        m = self.kb.move(name)
        return {"name": name, "pp": m["pp"], "type": m["type"]}

    def snapshot(self) -> dict:
        v = self.cfg["world"].get("vision", {})
        # 1. Read both actives off the action-menu panels.
        panels = read_panels(self._frame(), self._ocr_engine(), self.kb, _layout.ACTION)
        self._update_active("_self", panels["self"])
        self._update_active("_opp", panels["opp"])
        if self._self is None or self._opp is None:
            raise RuntimeError(
                "Could not read both Pokémon from the action panels — calibrate "
                "opp_name/self_name in vision/layout.py (ACTION)."
            )
        # 2. Open the move list (BATTLE = A) and read it via the KB.
        self._keyboard().press("a")
        time.sleep(v.get("menu_wait", 0.6))          # let the move menu animate in
        move_names = read_moves(self._frame(), self._ocr_engine(), self.kb, _layout.MOVES)
        if move_names:
            self._self["moves"] = [self._move_entry(n) for n in move_names]
        return self._build_snapshot()

    def _build_snapshot(self) -> dict:
        me, opp = self._self, self._opp
        return {
            "awaiting": "move" if me["moves"] else None,
            "self": {
                "dex": me["dex"], "hp": me["hp"], "max_hp": me["max_hp"], "status": None,
                "stages": {},
                "moves": [{"name": mv["name"], "pp": mv["pp"]} for mv in me["moves"]],
            },
            "self_party": [],   # party isn't visible from one screen; no switching in v1
            "opp": {"dex": opp["dex"], "hp": opp["hp"], "max_hp": opp["max_hp"], "status": None},
        }

    # ---- act ---------------------------------------------------------------
    def send_action(self, action: Action) -> None:
        self.pending = action

    def step(self) -> None:
        """Actuate the queued move on the already-open move menu, then let it animate.
        With no pending action, poll-sleep so the awaiting_input wait doesn't busy-spin."""
        v = self.cfg["world"].get("vision", {})
        action, self.pending = self.pending, None
        if action is None:
            time.sleep(v.get("poll", 0.3))
            return
        # v1 only attacks (switching from the action menu is a follow-up); a move
        # navigates the open menu and confirms.
        self._keyboard().tap_sequence(_MOVE_KEYS.get(action.index, ["a"]))
        time.sleep(v.get("turn_wait", 4.0))

    # ---- close out ---------------------------------------------------------
    def is_over(self) -> bool:
        return self._done

    def result(self) -> dict:
        return {"winner": None, "player_remaining": None, "opponent_remaining": None}
