#!/usr/bin/env python3
"""PTY-backed emulator for the read-only test protocol profile."""
import argparse
import json
import os
import pty
import select
import sys
import time
from pathlib import Path

from protocol import Profile, parse_one


class Emulator:
    def __init__(self, master_fd, config_path, fixtures, args):
        self.master_fd = master_fd
        self.config = json.loads(Path(config_path).read_text())
        self.profile = Profile.load(config_path)
        self.fixtures = Path(fixtures)
        self.args = args
        self.buffer = bytearray()
        self.response_count = 0
        self.counter = 0

    def get_response(self, request):
        command, address, length, _raw = request
        if command == "SPIR":
            if self.args.counter_per_spir:
                payload = bytes([self.counter]) * length
                self.counter = (self.counter + 1) & 0xff
                return payload
            flash = (self.fixtures / "flash.bin").read_bytes()
            if address + length > len(flash):
                print(f"SPIR out of fixture range: {address}+{length}", file=sys.stderr)
                return b""
            return flash[address:address + length]

        filename = self.config["responses"].get(command)
        if filename is None:
            print(f"Unknown command (no response): {command!r}", file=sys.stderr)
            return None
        path = self.fixtures / filename
        return path.read_bytes()

    def send_response(self, payload):
        if payload is None:
            return
        self.response_count += 1
        if self.args.drop_every and self.response_count % self.args.drop_every == 0:
            print(f"FAULT: dropped response #{self.response_count}", file=sys.stderr)
            return
        if self.args.response_delay:
            time.sleep(self.args.response_delay)
        if self.args.short_by:
            payload = payload[:-self.args.short_by] if self.args.short_by < len(payload) else b""
        chunk_size = self.args.fragment_size or max(1, len(payload))
        for pos in range(0, len(payload), chunk_size):
            os.write(self.master_fd, payload[pos:pos + chunk_size])
            if self.args.fragment_delay:
                time.sleep(self.args.fragment_delay)

    def run(self):
        print("PTY emulator running; Ctrl-C to stop.", file=sys.stderr)
        while True:
            ready, _, _ = select.select([self.master_fd], [], [], 0.5)
            if not ready:
                continue
            try:
                chunk = os.read(self.master_fd, 4096)
            except OSError as exc:
                # EIO can occur briefly before a client opens the slave PTY.
                if getattr(exc, "errno", None) == 5:
                    time.sleep(0.05)
                    continue
                raise
            if not chunk:
                continue
            self.buffer.extend(chunk)
            while self.buffer:
                request, consumed = parse_one(bytes(self.buffer), self.profile)
                if request is None:
                    break
                del self.buffer[:consumed]
                command, address, length, raw = request
                print(f"RX {raw.hex()} -> {command} address={address} length={length}",
                      file=sys.stderr)
                try:
                    self.send_response(self.get_response(request))
                except Exception as exc:
                    print(f"emulator error: {exc}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/device.json")
    ap.add_argument("--fixtures", default="fixtures")
    ap.add_argument("--fragment-size", type=int, default=0)
    ap.add_argument("--fragment-delay", type=float, default=0.0)
    ap.add_argument("--response-delay", type=float, default=0.0)
    ap.add_argument("--short-by", type=int, default=0)
    ap.add_argument("--drop-every", type=int, default=0)
    ap.add_argument("--counter-per-spir", action="store_true")
    args = ap.parse_args()
    if min(args.fragment_size, args.short_by, args.drop_every) < 0:
        ap.error("fault parameters must be non-negative")
    if min(args.fragment_delay, args.response_delay) < 0:
        ap.error("delays must be non-negative")

    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    # Keep slave open for the emulator lifetime to avoid master-side EIO before
    # the receiver opens the path. The receiver still opens its own slave fd.
    print(slave_path, flush=True)
    try:
        Emulator(master_fd, args.config, args.fixtures, args).run()
    except KeyboardInterrupt:
        pass
    finally:
        os.close(slave_fd)
        os.close(master_fd)


if __name__ == "__main__":
    main()
