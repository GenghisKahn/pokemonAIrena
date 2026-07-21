#!/usr/bin/env python3
"""Live probe for a running RetroArch — does the Network Control Interface answer,
and does the loaded core expose a memory map?

Run this once RetroArch is up with a core + ROM loaded and network commands on
(Settings > Network > Network Commands). It is safe: read-only, one-second timeout.

    python scripts/probe_retroarch.py [--host 127.0.0.1] [--port 55355] [--addr 0]

Exit code 0 means RetroArch answered; non-zero means no response / no memory map.
"""
from __future__ import annotations

import argparse
import socket
import sys


def send(sock: socket.socket, host: str, port: int, text: str) -> str:
    sock.sendto(text.encode("ascii"), (host, port))
    try:
        return sock.recv(4096).decode("ascii", "replace").strip()
    except socket.timeout:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=55355)
    ap.add_argument("--addr", default="0", help="hex address to test-read (default 0)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)

    print(f"probing RetroArch NCI at {args.host}:{args.port} (UDP)\n")

    status = send(sock, args.host, args.port, "GET_STATUS")
    if not status:
        print("✗ no response.")
        print("  Is RetroArch running with network commands enabled")
        print("  (Settings > Network > Network Commands, port 55355)?")
        return 1
    print(f"✓ GET_STATUS -> {status}")

    version = send(sock, args.host, args.port, "VERSION")
    if version:
        print(f"✓ VERSION    -> {version}")

    addr = int(args.addr, 16)
    mem = send(sock, args.host, args.port, f"READ_CORE_MEMORY {addr:x} 2")
    parts = mem.split()
    if not mem:
        print(f"✗ READ_CORE_MEMORY {addr:x} -> no response")
    elif len(parts) >= 3 and parts[2] == "-1":
        print(f"✗ READ_CORE_MEMORY {addr:x} -> error: {' '.join(parts[3:]) or 'no memory map'}")
        print("  The loaded core exposes no memory map at this address.")
        print("  For N64, use Mupen64Plus-Next (it maps RDRAM for RetroAchievements).")
    else:
        print(f"✓ READ_CORE_MEMORY {addr:x} -> {' '.join(parts[2:])}")
        print("\nMemory reads work. Next: find the battle-struct addresses (build step 2).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
