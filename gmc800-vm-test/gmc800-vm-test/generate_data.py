#!/usr/bin/env python3
"""Generate constant, seeded-PRNG, or incrementing-byte binary fixtures."""
import argparse
import hashlib
import json
import random
from pathlib import Path


def make_bytes(size, pattern, value=0, seed=1, offset=0):
    if size < 0:
        raise ValueError("size must be non-negative")
    if not 0 <= value <= 255:
        raise ValueError("value must be in 0..255")
    if pattern == "constant":
        return bytes([value]) * size
    if pattern == "counter":
        return bytes((offset + i) & 0xff for i in range(size))
    if pattern == "prng":
        rng = random.Random(seed)
        # getrandbits works on Python versions predating Random.randbytes().
        return bytes(rng.getrandbits(8) for _ in range(size))
    raise ValueError(f"unknown pattern: {pattern}")


def write_set(root, cfg_size, flash_size, pattern, value, seed, offset):
    root.mkdir(parents=True, exist_ok=True)
    data = {
        "cfg.bin": make_bytes(cfg_size, pattern, value, seed, offset),
        "flash.bin": make_bytes(flash_size, pattern, value, seed ^ 0x800, offset),
    }
    data.update({
        "GETVER.bin": b"GMC-800Re2.01",
        "GETSERIAL.bin": b"TEST-SERIAL-0001",
        "GETCPM.bin": (123).to_bytes(4, "big"),
        "GETCPS.bin": (2).to_bytes(4, "big"),
        "GETVOLT.bin": b"3500 ",
        "GETDATETIME.bin": bytes([0x20, 0x26, 0x11, 0x07, 0x12, 0x00, 0x00]),
    })
    for name, content in data.items():
        (root / name).write_bytes(content)
    metadata = {
        "pattern": pattern, "value": value, "seed": seed, "offset": offset,
        "cfg_size": cfg_size, "flash_size": flash_size,
        "sha256": {name: hashlib.sha256(content).hexdigest()
                   for name, content in data.items()},
    }
    (root / "fixture.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="fixtures")
    ap.add_argument("--cfg-size", type=int, default=512)
    ap.add_argument("--flash-size", type=int, default=65536)
    ap.add_argument("--pattern", choices=("constant", "prng", "counter"), default="prng")
    ap.add_argument("--value", type=lambda x: int(x, 0), default=0xA5)
    ap.add_argument("--seed", type=int, default=800)
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--sweep-constant", action="store_true",
                    help="create 256 directories filled with byte values 00..ff")
    args = ap.parse_args()
    if args.cfg_size < 0 or args.flash_size < 0:
        ap.error("sizes must be non-negative")
    if not 0 <= args.value <= 255:
        ap.error("--value must be in 0..255")
    out = Path(args.out)
    if args.sweep_constant:
        for value in range(256):
            write_set(out / f"{value:02x}", args.cfg_size, args.flash_size,
                      "constant", value, args.seed, 0)
    else:
        write_set(out, args.cfg_size, args.flash_size, args.pattern,
                  args.value, args.seed, args.offset)
    print(f"fixtures written under {out}")


if __name__ == "__main__":
    main()
