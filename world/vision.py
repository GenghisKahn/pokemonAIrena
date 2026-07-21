"""vision — a Backend that plays the REAL Pokemon Stadium on RetroArch, no RAM map.

The split that makes this tractable: a battle's *static* roster (species, movepools,
PP, base stats) is known before the match from config.yaml — you don't OCR your own
team. Vision only tracks the *dynamic* state that changes turn to turn:

  * which Pokemon is active on each side  (OCR the name, match it to the roster)
  * your active's current HP               (OCR the HP number)
  * whether the game awaits a move          (OCR the move-menu region for known moves)

State (observe) comes from `vision/` (capture + Apple Vision OCR); actions (act) go out
through `world/keyboard.py` as RetroArch RetroPad keystrokes. read_battle() sees the
same snapshot shape as the mock, so the harness loop is unchanged.

⚠️ CALIBRATE before trusting a live run (none of this is verifiable headless):
  1. `python scripts/ocr_probe.py --region x,y,w,h --regions` to line up vision/layout.py
     against a real Stadium battle frame.
  2. Grant Accessibility permission to your terminal (keyboard events; see world/keyboard.py).
  3. Check the move-menu / switch-menu keystroke maps below against your RetroArch binds.
"""
from __future__ import annotations

import time

from battle.damage import battle_stats
from battle.state import Action
from kb import KB, default_kb
from vision import layout as _layout
from vision.capture import capture_region, crop_norm
from vision.observe import match_species, read_screen

# Move menu is a 2x2 grid; cursor rests on slot 0 (top-left) when the menu opens.
# RetroPad button sequence to land on each slot and confirm. CALIBRATE to your ROM.
_MOVE_KEYS = {
    0: ["a"],                       # top-left
    1: ["right", "a"],              # top-right
    2: ["down", "a"],               # bottom-left
    3: ["down", "right", "a"],      # bottom-right
}


class _Mon:
    """A roster entry: static team data + a mutable current-HP the OCR read updates."""
    def __init__(self, kb: KB, species: str, move_names: list[str], level: int):
        sp = kb.species(species)
        self.name = species
        self.dex = sp["dex"]
        self.types = tuple(sp["types"])
        stats = battle_stats(sp["base"], level)
        self.max_hp = stats["hp"]
        self.hp = stats["hp"]
        self.status: str | None = None
        self.moves = [
            {"name": mn, "pp": kb.move(mn)["pp"], "type": kb.move(mn)["type"]}
            for mn in move_names
        ]


class VisionBackend:
    """Observe Stadium via OCR, act via the keyboard. Static roster + dynamic OCR."""

    def __init__(self, cfg: dict, ocr=None, keyboard=None):
        self.cfg = cfg
        self.kb = default_kb()
        self.level = cfg["world"].get("level", 50)
        v = cfg["world"].get("vision", {})
        self.region = tuple(v["region"]) if v.get("region") else None   # capture rect (points)
        self.regions = _layout.BATTLE
        # Injected for tests; built lazily on a real run so no OCR engine is needed to import.
        self._ocr = ocr
        self._kb_input = keyboard
        self.reset()

    # ---- roster (static, from config) --------------------------------------
    def _team(self, spec: list) -> list[_Mon]:
        return [_Mon(self.kb, e["species"], e["moves"], self.level) for e in spec]

    def reset(self) -> None:
        b = self.cfg["battle"]
        self.teams = [self._team(b["player_team"]), self._team(b["opponent_team"])]
        self.active = [0, 0]
        self.pending: Action | None = None

    # ---- dependencies (lazy on real runs) ----------------------------------
    def _ocr_engine(self):
        if self._ocr is None:
            from vision.ocr import default_ocr
            self._ocr = default_ocr()
        return self._ocr

    def _keyboard(self):
        if self._kb_input is None:
            from world import keyboard
            keyboard.activate_retroarch()
            self._kb_input = keyboard
        return self._kb_input

    def _frame(self):
        return capture_region(self.region)

    # ---- observe -----------------------------------------------------------
    def _sync_from_screen(self) -> dict:
        """OCR the frame; update actives + your HP from what's on screen.

        Returns the raw read so awaiting_input()/snapshot() can reuse it without a
        second capture. Unmatched reads leave the last-known state intact (a missed
        frame must not corrupt the battle state)."""
        img = self._frame()
        obs = read_screen(img, self._ocr_engine(), self.kb, self.regions)
        self._match_active(0, obs["self"]["name"])
        self._match_active(1, obs["opp"]["name"])
        me = self.teams[0][self.active[0]]
        if obs["self"]["hp"] is not None:
            me.hp = max(0, min(me.max_hp, obs["self"]["hp"]))
        return obs

    def _match_active(self, side: int, name: str | None) -> None:
        if not name:
            return
        for i, mon in enumerate(self.teams[side]):
            if mon.name == name:
                self.active[side] = i
                return

    def snapshot(self) -> dict:
        self._sync_from_screen()
        me = self.teams[0][self.active[0]]
        opp = self.teams[1][self.active[1]]
        party = [
            {"dex": m.dex, "hp": m.hp, "max_hp": m.max_hp, "status": m.status}
            for i, m in enumerate(self.teams[0]) if i != self.active[0]
        ]
        return {
            "awaiting": "move" if self.awaiting_input() else None,
            "self": {
                "dex": me.dex, "hp": me.hp, "max_hp": me.max_hp, "status": me.status,
                "stages": {},
                "moves": [{"name": mv["name"], "pp": mv["pp"]} for mv in me.moves],
            },
            "self_party": party,
            "opp": {"dex": opp.dex, "hp": opp.hp, "max_hp": opp.max_hp, "status": opp.status},
        }

    def awaiting_input(self) -> bool:
        """The game awaits a move when the move-menu region shows the active's moves."""
        img = self._frame()
        text = " ".join(
            r.text for r in self._ocr_engine().recognize(crop_norm(img, self.regions["self_name"]))
        )
        # Heuristic: a battle frame that reads the active's name is in-battle; refine
        # with a dedicated move-menu region once layout.py is calibrated (see docstring).
        me = self.teams[0][self.active[0]]
        return bool(match_species(text, self.kb) == me.name) and not self.is_over()

    # ---- act ---------------------------------------------------------------
    def send_action(self, action: Action) -> None:
        self.pending = action

    def step(self) -> None:
        """Actuate the queued action via keystrokes, then let the turn animate."""
        action, self.pending = self.pending, None
        if action is None:
            return
        kb = self._keyboard()
        if action.kind == "move":
            kb.tap_sequence(_MOVE_KEYS.get(action.index, ["a"]))
        else:
            kb.tap_sequence(self._switch_keys(action.index))
        time.sleep(self.cfg["world"].get("vision", {}).get("turn_wait", 4.0))  # animations

    def _switch_keys(self, party_index: int) -> list[str]:
        """Open the switch menu and land on a bench slot. CALIBRATE to your ROM's flow."""
        return ["b", "down"] + ["down"] * party_index + ["a", "a"]

    # ---- close out ---------------------------------------------------------
    def is_over(self) -> bool:
        return any(all(m.hp <= 0 for m in team) for team in self.teams)

    def result(self) -> dict:
        p = sum(m.hp > 0 for m in self.teams[0])
        o = sum(m.hp > 0 for m in self.teams[1])
        winner = "player" if o == 0 and p else "opponent" if p == 0 and o else None
        return {"winner": winner, "player_remaining": p, "opponent_remaining": o}
