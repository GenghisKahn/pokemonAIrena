"""Entry point: run one battle with the configured backend and player.

    python app.py            # play the default battle, printing each turn
    python app.py --quiet    # just the final result
"""
from __future__ import annotations

import sys

import yaml

from agent.player import make_player
from harness.loop import battle
from kb import default_kb
from world.base import make_backend


def _print_turn(p: dict) -> None:
    blocks = ("  [blocked: " + "; ".join(p["blocks"]) + "]") if p["blocks"] else ""
    print(f"T{p['turn']:>3}  {p['self']:<28} vs {p['opp']:<28}  {p['action']['label']}{blocks}")


def main() -> None:
    quiet = "--quiet" in sys.argv
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    kb = default_kb()
    backend = make_backend(cfg)
    player = make_player(cfg)

    result = battle(backend, player, kb, cfg, emit=None if quiet else _print_turn)

    print("-" * 72)
    print(f"winner: {result['winner']}   turns: {result['turns']}   "
          f"remaining {result['player_remaining']}-{result['opponent_remaining']}   "
          f"blocks: {len(result['blocks'])}")


if __name__ == "__main__":
    main()
