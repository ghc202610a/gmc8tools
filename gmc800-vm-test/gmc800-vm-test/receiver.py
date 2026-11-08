#!/usr/bin/env python3
"""Bounded-timeout raw serial receiver for the emulator test profile."""
import argparse
import hashlib
import json
import os
import select
import termios
import time
from pathlib import Path

from protocol import Profile, encode_command, encode_spir


def read_exact(fd, count, timeout):
    received = bytearray()
    deadline = time.monotonic() + timeout
    while len(received) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return bytes(received), "timeout"
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            return bytes(received), "timeout"
        try:
            chunk = os.read(fd, count - len(received))
        except BlockingIOError:
            continue
        if not chunk:
            return bytes(received), "eof"
        received.extend(chunk)
    return bytes(received), "complete"


def configure_tty(fd, baud):
    speed = getattr(termios, f"B{baud}", None)
    if speed is None:
        raise ValueError(f"unsupported local termios baud constant: {baud}")
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def record_file(outdir, relative_name, data, status, expected, records):
    path = outdir / relative_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    records.append({
        "file": relative_name,
        "status": status,
        "expected_bytes": expected,
        "received_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--config", default="config/device.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--flash-size", type=lambda x: int(x, 0), default=65536)
    ap.add_argument("--block-size", type=int, default=256)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--skip-commands", action="store_true")
    args = ap.parse_args()
    if args.flash_size < 0 or args.block_size < 1 or args.timeout <= 0:
        ap.error("flash size must be nonnegative; block size and timeout must be positive")

    config = json.loads(Path(args.config).read_text())
    profile = Profile.load(args.config)
    if args.block_size > profile.max_request_length:
        ap.error("block size exceeds configured SPIR maximum")
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    records = []
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    flash_complete = True
    try:
        configure_tty(fd, int(config.get("baud", 115200)))

        if not args.skip_commands:
            for command, filename in config["responses"].items():
                expected = int(config["expected_lengths"][command])
                os.write(fd, encode_command(command, profile))
                data, status = read_exact(fd, expected, args.timeout)
                record_file(outdir, f"responses/{filename}", data, status,
                            expected, records)

        blocks = []
        address = 0
        index = 0
        while address < args.flash_size:
            length = min(args.block_size, args.flash_size - address)
            os.write(fd, encode_spir(address, length, profile))
            data, status = read_exact(fd, length, args.timeout)
            record_file(outdir, f"spir/block_{index:06d}.bin", data,
                        status, length, records)
            blocks.append(data)
            if status != "complete":
                flash_complete = False
                break
            address += length
            index += 1

        flash_data = b"".join(blocks)
        (outdir / "flash.bin").write_bytes(flash_data)
        manifest = {
            "port": args.port,
            "baud": int(config.get("baud", 115200)),
            "flash_requested_bytes": args.flash_size,
            "flash_received_bytes": len(flash_data),
            "flash_status": "complete" if flash_complete and len(flash_data) == args.flash_size else "incomplete",
            "flash_sha256": hashlib.sha256(flash_data).hexdigest(),
            "profile_note": "Configurable test profile; verify framing and lengths before real-device use.",
            "records": records,
        }
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(manifest, indent=2))
        incomplete = (not flash_complete or len(flash_data) != args.flash_size
                      or any(item["status"] != "complete" for item in records))
        raise SystemExit(2 if incomplete else 0)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
