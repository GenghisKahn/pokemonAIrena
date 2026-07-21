#!/usr/bin/env python3
"""RAM search over RetroArch's Network Control Interface — the instrument that
turns "we read bytes" into "we know which address is HP".

Classic value search: you know a number on screen (your Pokemon's HP), find every
address that currently holds it, change it (take damage), keep only the addresses
that now hold the new value, and repeat until one survives. That address goes in
world/retroarch.py's _ADDR table.

Requires RetroArch running with a core + ROM, in a battle, network commands on
(Settings > Network > Network Commands, port 55355). N64: use Mupen64Plus-Next,
whose memory map exposes RDRAM (ParaLLEl-N64 may not).

Workflow:
    python scripts/ram_search.py new --value 166 --size 2          # first pass
    # ... take damage in-game so HP changes to, say, 46 ...
    python scripts/ram_search.py filter --value 46                 # narrow
    # repeat filter until a handful remain, then:
    python scripts/ram_search.py watch --addr 0x1c210 --size 2     # confirm it tracks HP

Endianness: N64 is big-endian; try --endian big first, then little if nothing sticks.
State lives in .ram_search.json (the surviving candidate set between passes).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

STATE = Path(".ram_search.json")


class NCI:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)

    def _cmd(self, text: str) -> str:
        self.sock.sendto(text.encode("ascii"), (self.host, self.port))
        try:
            return self.sock.recv(65535).decode("ascii", "replace").strip()
        except socket.timeout:
            return ""

    def read(self, address: int, n: int) -> bytes | None:
        reply = self._cmd(f"READ_CORE_MEMORY {address:x} {n}")
        parts = reply.split()
        if len(parts) < 3 or parts[2] == "-1":
            return None
        try:
            return bytes(int(b, 16) for b in parts[2:])
        except ValueError:
            return None

    def read_region(self, start: int, length: int, chunk: int = 512) -> dict[int, int]:
        """Read [start, start+length) as {address: byte}. Skips unreadable chunks."""
        mem: dict[int, int] = {}
        addr = start
        end = start + length
        while addr < end:
            n = min(chunk, end - addr)
            data = self.read(addr, n)
            if data is not None:
                for i, b in enumerate(data):
                    mem[addr + i] = b
            addr += n
        return mem


def _val_at(mem: dict[int, int], addr: int, size: int, endian: str):
    try:
        raw = bytes(mem[addr + i] for i in range(size))
    except KeyError:
        return None
    return int.from_bytes(raw, endian)


def _read_val(nci: NCI, addr: int, size: int, endian: str):
    data = nci.read(addr, size)
    return None if data is None else int.from_bytes(data, endian)


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state))


def _load() -> dict:
    if not STATE.exists():
        sys.exit("no search in progress — run `new` first.")
    return json.loads(STATE.read_text())


def cmd_new(nci: NCI, args) -> None:
    start, length = _parse_region(args.region)
    print(f"reading {length:#x} bytes from {start:#x} ({args.endian}-endian, size {args.size})...")
    mem = nci.read_region(start, length, args.chunk)
    if not mem:
        sys.exit("no memory read — is RetroArch running with a core + network commands?")
    hits = [a for a in range(start, start + length - args.size + 1)
            if _val_at(mem, a, args.size, args.endian) == args.value]
    _save({"size": args.size, "endian": args.endian, "value": args.value,
           "candidates": [f"{a:x}" for a in hits]})
    print(f"{len(hits)} address(es) hold {args.value}. Change the value in-game, then `filter`.")


def cmd_filter(nci: NCI, args) -> None:
    st = _load()
    size, endian = st["size"], st["endian"]
    survivors = []
    for hx in st["candidates"]:
        addr = int(hx, 16)
        if _read_val(nci, addr, size, endian) == args.value:
            survivors.append(hx)
    st["candidates"], st["value"] = survivors, args.value
    _save(st)
    print(f"{len(survivors)} address(es) now hold {args.value}:")
    for hx in survivors[:20]:
        print(f"  0x{hx}")
    if len(survivors) > 20:
        print(f"  ... and {len(survivors) - 20} more")
    if len(survivors) == 1:
        print(f"\nlikely address: 0x{survivors[0]}  — confirm with `watch --addr 0x{survivors[0]}`")


def cmd_watch(nci: NCI, args) -> None:
    print(f"watching 0x{args.addr:x} ({args.size} bytes, {args.endian}) — Ctrl-C to stop")
    last = object()
    for _ in range(args.count):
        v = _read_val(nci, args.addr, args.size, args.endian)
        if v != last:
            print(f"  0x{args.addr:x} = {v}")
            last = v
        time.sleep(args.interval)


def _parse_region(text: str) -> tuple[int, int]:
    start_s, len_s = text.split(":")
    return int(start_s, 0), int(len_s, 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=55355)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="start a search for --value across a region")
    p_new.add_argument("--value", type=lambda x: int(x, 0), required=True)
    p_new.add_argument("--size", type=int, default=2, help="value width in bytes (1/2/4)")
    p_new.add_argument("--endian", choices=["big", "little"], default="big")
    p_new.add_argument("--region", default="0x0:0x400000", help="start:length (N64 RDRAM = 0x0:0x400000)")
    p_new.add_argument("--chunk", type=int, default=512)

    p_filter = sub.add_parser("filter", help="keep candidates now holding --value (size/endian from the saved search)")
    p_filter.add_argument("--value", type=lambda x: int(x, 0), required=True)

    p_watch = sub.add_parser("watch", help="poll one address to confirm it tracks the value")
    p_watch.add_argument("--addr", type=lambda x: int(x, 0), required=True)
    p_watch.add_argument("--size", type=int, default=2, help="value width in bytes (1/2/4)")
    p_watch.add_argument("--endian", choices=["big", "little"], default="big")
    p_watch.add_argument("--count", type=int, default=200)
    p_watch.add_argument("--interval", type=float, default=0.5)

    args = ap.parse_args()
    nci = NCI(args.host, args.port)
    {"new": cmd_new, "filter": cmd_filter, "watch": cmd_watch}[args.cmd](nci, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
