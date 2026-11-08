Contents
File	Purpose
emulator.py	PTY-backed device protocol emulator
receiver.py	Bounded-timeout serial receiver
generate_data.py	Binary fixture generator
protocol.py	Shared protocol framing and parser
config/device.json	Configurable command and response profile
fixtures/	Example CFG, flash and command responses
tests/	Protocol and data-pattern tests
README.md	Setup, usage and protocol caveats

Data generation modes
- Constant byte fill, e.g. 0xA7.
- Seeded PRNG data, reproducible across runs.
- Incrementing sequence 00 01 ... FF 00 ....
- 256 separate fixture sets, each filled with one of 0x00 through 0xFF.
- Dynamic SPIR responses: each successive request returns a block filled with the next byte value, wrapping after 0xFF.
Extraction and initial test
chmod +x gmc800-vm-test.shar
./gmc800-vm-test.shar
cd gmc800-vm-test
python3 -m unittest discover -s tests -v


Six unit tests passed. I also ran an end-to-end PTY test: the receiver retrieved command responses and a 1,024-byte flash image, and the reconstructed image compared byte-for-byte with the fixture.

First emulator/receiver run

Terminal 1:
python3 emulator.py --config config/device.json --fixtures fixtures


Terminal 2, using the PTY path printed by the emulator:
python3 receiver.py \
    --port /dev/pts/N \
    --config config/device.json \
    --out captures/test-001 \
    --flash-size 65536 \
    --block-size 256


For the dynamic 256-value test, start the emulator with:
python3 emulator.py --config config/device.json \
    --fixtures fixtures --counter-per-spir


Then use the same receiver command. With 65,536 bytes and 256-byte blocks, it will issue 256 SPIR requests, producing one block for each byte value from 00 through FF.

Important limitation: the framing profile is deliberately provisional. In particular, the SPIR field encoding, terminator, and response lengths must be verified against actual GMC-800 traffic before connecting this receiver to the meter. This is currently a desktop protocol test harness, not a validated acquisition client.

A useful next increment would be adding a transcript mode that records every transmitted request and received byte sequence with monotonic timestamps, so emulator and receiver behavior can be compared exactly.

