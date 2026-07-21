"""Validate the RetroArch NCI client against a mock Network Control Interface.

RetroArch isn't needed for this test: a tiny UDP server speaks the exact
READ_CORE_MEMORY / WRITE_CORE_MEMORY reply format the real frontend uses, so we
prove our request formatting and hex parsing are correct. When pointed at a real
RetroArch (same protocol), read_memory/write_memory will behave identically.
"""
from __future__ import annotations

import socket
import threading

from world.retroarch import RetroArchBackend

# Fake core memory the mock server serves, keyed by address.
_FAKE_MEM = {0x100: 0x00, 0x101: 0x9C}   # e.g. a u16 HP = 0x009C = 156


def _mock_nci_server(sock: socket.socket, stop: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        parts = data.decode("ascii").split()
        cmd = parts[0]
        if cmd == "READ_CORE_MEMORY":
            base, n = int(parts[1], 16), int(parts[2])
            vals = [_FAKE_MEM.get(base + i, 0) for i in range(n)]
            reply = f"READ_CORE_MEMORY {base:x} " + " ".join(f"{v:02x}" for v in vals)
            sock.sendto(reply.encode("ascii"), addr)
        elif cmd == "WRITE_CORE_MEMORY":
            base = int(parts[1], 16)
            nbytes = len(parts) - 2
            for i, b in enumerate(parts[2:]):
                _FAKE_MEM[base + i] = int(b, 16)
            sock.sendto(f"WRITE_CORE_MEMORY {base:x} {nbytes}".encode("ascii"), addr)
        elif cmd == "GET_STATUS":
            sock.sendto(b"GET_STATUS PLAYING mupen64plus_next,Pokemon Stadium,crc32=deadbeef", addr)


def _backend_against_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    stop = threading.Event()
    thread = threading.Thread(target=_mock_nci_server, args=(srv, stop), daemon=True)
    thread.start()
    cfg = {"world": {"retroarch": {"host": "127.0.0.1", "port": port}}}
    return RetroArchBackend(cfg), srv, stop, thread


def test_read_memory_parses_hex_bytes():
    be, srv, stop, thread = _backend_against_server()
    try:
        assert be.read_memory(0x100, 2) == b"\x00\x9c"
    finally:
        stop.set(); thread.join(); srv.close()


def test_write_then_read_roundtrips():
    be, srv, stop, thread = _backend_against_server()
    try:
        be.write_memory(0x200, b"\x2a")
        assert be.read_memory(0x200, 1) == b"\x2a"
    finally:
        stop.set(); thread.join(); srv.close()
