# GMC-800 desktop / VM protocol test kit

A Python 3 standard-library-only prototype for testing a read-only receiver against a synthetic serial device. The desktop transport is a PTY. It does **not** emulate USB enumeration or CDC-ACM descriptors.

## Protocol status

The GMC-800 protocol is not fully established here. This kit therefore uses an explicit, editable test profile rather than claiming that every framing detail is confirmed for firmware Re2.01.

The sample profile assumes:

- Ordinary commands are ASCII command names followed by `>>`.
- A SPIR request is `SPIR`, three binary address bytes (A2,A1,A0), two binary length bytes (L1,L0), then `>>`.
- SPIR address and length fields are big-endian.
- SPIR responses contain exactly the requested number of bytes, with no additional framing.

These are test-profile assumptions. Confirm them against reliable GMC-800 documentation or captured traffic before using the receiver with the physical meter. All framing and expected response lengths are configurable.

The emulator implements only read-only requests: `GETVER`, `GETSERIAL`, `GETCFG`, `GETCPM`, `GETCPS`, `GETVOLT`, `GETDATETIME`, and `SPIR`. It does not implement reset, power, configuration-write, key, speaker, alarm, or time-setting commands. Unknown commands receive no response.

## Contents

- `emulator.py` — PTY-backed protocol emulator.
- `receiver.py` — bounded-timeout receiver; stores raw response files and a JSON manifest.
- `generate_data.py` — generates constant, seeded PRNG, and incrementing-byte fixtures; can generate all 256 constant-byte fixture sets.
- `protocol.py` — shared framing profile and parser.
- `config/device.json` — sample protocol and response-length configuration.
- `fixtures/` — deterministic example CFG/flash and read-only command responses.
- `tests/` — unit tests for request parsing and fixture patterns.

## Quick start

Run from the extracted project directory.

Generate deterministic sample data:

```sh
python3 generate_data.py --out fixtures --cfg-size 512 --flash-size 65536 \
  --pattern prng --seed 800
```

Terminal 1 — start the emulator:

```sh
python3 emulator.py --config config/device.json --fixtures fixtures
```

It prints a PTY path such as `/dev/pts/8`. Keep this process running.

Terminal 2 — run the receiver, substituting the printed PTY path:

```sh
python3 receiver.py --port /dev/pts/8 --config config/device.json \
  --out captures/test-001 --flash-size 65536 --block-size 256
```

The receiver stores command responses under `responses/`, individual SPIR blocks under `spir/`, a reconstructed `flash.bin`, and `manifest.json`. A timeout, short response, or incomplete flash dump causes a nonzero exit status. Partial bytes are preserved and identified as incomplete.

## Fixture generation modes

Constant fill:

```sh
python3 generate_data.py --out fixtures --cfg-size 512 --flash-size 65536 \
  --pattern constant --value 0xA7
```

Seeded deterministic PRNG data:

```sh
python3 generate_data.py --out fixtures --pattern prng --seed 800
```

Incrementing byte sequence (`00 01 ... ff 00 01 ...`):

```sh
python3 generate_data.py --out fixtures --pattern counter --offset 0x00
```

Generate 256 separate fixture sets, each filled with one byte value from `0x00` through `0xff`:

```sh
python3 generate_data.py --out sweep --cfg-size 512 --flash-size 4096 \
  --sweep-constant
```

This creates `sweep/00/{cfg.bin,flash.bin}` through `sweep/ff/{cfg.bin,flash.bin}`.

## Dynamic response counter

To make each SPIR response a different constant byte, incrementing from `0x00` through `0xff` and wrapping:

```sh
python3 emulator.py --config config/device.json --fixtures fixtures \
  --counter-per-spir
```

The counter advances once per SPIR request. This tests response sequencing independently of the flash fixture. The emulator still responds to non-SPIR commands using the configured fixture files.

## Fault injection

Fragment responses into chunks of at most seven bytes, with a 10 ms gap:

```sh
python3 emulator.py --config config/device.json --fixtures fixtures \
  --fragment-size 7 --fragment-delay 0.01
```

Other options:

```sh
--response-delay 0.5   # delay before each response
--short-by 3           # truncate each response by three bytes
--drop-every 5         # suppress every fifth response
```

Use one fault mode at a time initially. The receiver has a per-response timeout, so delayed responses can intentionally produce incomplete records.

## Receiver behavior

The receiver opens the serial endpoint once and retains that file descriptor for the session. It configures raw 8N1 at the configured baud rate (115200 by default), uses `select()` with an absolute deadline, and reads exact byte counts. It does not use line-oriented reads and does not treat NUL as a terminator.

Expected lengths for ordinary command responses are in `config/device.json`. The sample `GETCFG` length is 512 and `GETCPM`/`GETCPS` are four bytes. Other sample lengths are illustrative and must be verified before real-device use. The emulator fixtures and receiver configuration should agree.

The sample SPIR maximum request length is 4096 bytes. The receiver's block size defaults to 256 and must not exceed the configured maximum.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Integrity

The receiver records SHA-256 for each saved response and for the reconstructed flash image. These hashes establish local file integrity after capture; they do not prove that a device supplied correct data. For physical-device validation, compare repeated reads and overlapping SPIR ranges. If the meter continues logging during capture, a full flash dump may not be an atomic snapshot; capturing CFG before and after can help identify state changes.

## VM and USB boundary

A PTY tests the serial byte stream and application protocol. It does not test USB enumeration, CDC descriptors, control requests, EHCI/xHCI, or a physical USB controller. QEMU can attach a PTY as a virtual serial port, but that still is not USB device emulation. A later `dummy_hcd`/USB-gadget or physical CDC-ACM board test is a separate stage.

## Safety of use

This is a test harness. Do not connect it to the real GMC-800 until the framing, byte order, response lengths, and timeout behavior have been independently checked. The receiver sends only the configured read-only commands and SPIR requests.
