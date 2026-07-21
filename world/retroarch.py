"""retroarch — macOS-native backend over the Network Control Interface (UDP).

The memory transport is real and works today: READ_CORE_MEMORY / WRITE_CORE_MEMORY
and save/load state over UDP (default port 55355). What's NOT done is the RAM map
(which addresses hold the battle struct) and the input path — RetroArch has no
network command that presses an in-game button, so send_action must either write
the controller-poll address or drive a virtual gamepad. Both are marked below.

Enable in RetroArch: Settings > Network > Network Commands.
"""
from __future__ import annotations

import socket

from battle.state import Action

# TODO(ram-map): fill these in during "map the battle struct" (build step 2).
# Start from community maps (DataCrystal / TCRF) and verify against a known HP value.
_ADDR: dict[str, int] = {
    # "self_hp": 0x...,
    # "opp_hp": 0x...,
    # "menu_state": 0x...,
}


class RetroArchBackend:
    def __init__(self, cfg: dict):
        ra = cfg["world"].get("retroarch", {})
        self.host = ra.get("host", "127.0.0.1")
        self.port = ra.get("port", 55355)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)

    # ---- working UDP transport ---------------------------------------------
    def _command(self, text: str) -> str:
        """Send one NCI command and return the reply (empty if none)."""
        self.sock.sendto(text.encode("ascii"), (self.host, self.port))
        try:
            return self.sock.recv(4096).decode("ascii", "replace").strip()
        except socket.timeout:
            return ""

    def read_memory(self, address: int, num_bytes: int) -> bytes:
        """READ_CORE_MEMORY <addr> <n>. Reply: 'READ_CORE_MEMORY <addr> <hex bytes...>'."""
        reply = self._command(f"READ_CORE_MEMORY {address:x} {num_bytes}")
        parts = reply.split()
        if len(parts) < 3 or parts[2] == "-1":
            raise RuntimeError(f"READ_CORE_MEMORY failed: {reply!r}")
        return bytes(int(b, 16) for b in parts[2:])

    def write_memory(self, address: int, data: bytes) -> None:
        payload = " ".join(f"{b:02x}" for b in data)
        self._command(f"WRITE_CORE_MEMORY {address:x} {payload}")

    def save_state(self) -> None:
        self._command("SAVE_STATE")

    def load_state(self) -> None:
        self._command("LOAD_STATE")

    # ---- Backend interface (needs the RAM map + an input path) --------------
    def reset(self) -> None:
        self.load_state()  # reset by loading a battle-start save state

    def snapshot(self) -> dict:
        raise NotImplementedError(
            "RAM map not defined yet. Decode the battle struct from read_memory() "
            "into the snapshot shape MockBattle returns. See _ADDR above."
        )

    def awaiting_input(self) -> bool:
        raise NotImplementedError("Read the menu-state byte to detect an awaiting turn.")

    def send_action(self, action: Action) -> None:
        raise NotImplementedError(
            "No NCI button command exists. Either WRITE_CORE_MEMORY to the "
            "controller-poll address, or drive a virtual gamepad, to navigate the menu."
        )

    def step(self) -> None:
        raise NotImplementedError("Let frames run until awaiting_input() is true again.")

    def is_over(self) -> bool:
        raise NotImplementedError("Detect the win/lose screen from RAM.")

    def result(self) -> dict:
        raise NotImplementedError
