"""Shared, configurable request framing for the emulator test profile."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    terminator: bytes
    spir_prefix: bytes
    address_bytes: int
    length_bytes: int
    byte_order: str
    max_request_length: int

    @classmethod
    def load(cls, path):
        obj = json.loads(Path(path).read_text())
        s = obj["spir"]
        order = s["byte_order"]
        if order not in ("big", "little"):
            raise ValueError("byte_order must be 'big' or 'little'")
        return cls(
            bytes.fromhex(obj["terminator_hex"]),
            s["prefix"].encode("ascii"),
            int(s["address_bytes"]),
            int(s["length_bytes"]),
            order,
            int(s["max_request_length"]),
        )

    @property
    def spir_request_size(self):
        return (len(self.spir_prefix) + self.address_bytes
                + self.length_bytes + len(self.terminator))


def parse_one(buffer: bytes, profile: Profile):
    """Return (request, consumed_bytes), or (None, 0) if incomplete."""
    if buffer.startswith(profile.spir_prefix):
        n = profile.spir_request_size
        if len(buffer) < n:
            return None, 0
        raw = buffer[:n]
        if not raw.endswith(profile.terminator):
            raise ValueError(f"malformed SPIR frame: {raw.hex()}")
        p = len(profile.spir_prefix)
        a = raw[p:p + profile.address_bytes]
        l = raw[p + profile.address_bytes:p + profile.address_bytes + profile.length_bytes]
        address = int.from_bytes(a, profile.byte_order)
        length = int.from_bytes(l, profile.byte_order)
        if length > profile.max_request_length:
            raise ValueError(f"SPIR length {length} exceeds configured maximum")
        return ("SPIR", address, length, raw), n

    i = buffer.find(profile.terminator)
    if i < 0:
        return None, 0
    token = buffer[:i]
    try:
        command = token.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"non-ASCII ordinary command: {token.hex()}") from exc
    return (command, None, None, token + profile.terminator), i + len(profile.terminator)


def encode_command(command: str, profile: Profile) -> bytes:
    return command.encode("ascii") + profile.terminator


def encode_spir(address: int, length: int, profile: Profile) -> bytes:
    if address < 0 or address >= (1 << (8 * profile.address_bytes)):
        raise ValueError("SPIR address out of range")
    if length < 0 or length >= (1 << (8 * profile.length_bytes)):
        raise ValueError("SPIR length out of range")
    if length > profile.max_request_length:
        raise ValueError("SPIR length exceeds configured maximum")
    return (profile.spir_prefix
            + address.to_bytes(profile.address_bytes, profile.byte_order)
            + length.to_bytes(profile.length_bytes, profile.byte_order)
            + profile.terminator)
