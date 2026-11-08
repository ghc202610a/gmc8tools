import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import Profile, encode_command, encode_spir, parse_one
from generate_data import make_bytes


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(b">>", b"SPIR", 3, 2, "big", 4096)

    def test_ordinary_command(self):
        raw = encode_command("GETVER", self.profile)
        request, used = parse_one(raw, self.profile)
        self.assertEqual(request[0], "GETVER")
        self.assertEqual(used, len(raw))

    def test_binary_spir_fields(self):
        raw = encode_spir(0x123456, 0x0102, self.profile)
        request, used = parse_one(raw, self.profile)
        self.assertEqual(request[:3], ("SPIR", 0x123456, 0x0102))
        self.assertEqual(used, len(raw))

    def test_fragmented_ordinary_command(self):
        raw = encode_command("GETCPM", self.profile)
        self.assertEqual(parse_one(raw[:3], self.profile), (None, 0))
        self.assertEqual(parse_one(raw, self.profile)[0][0], "GETCPM")

    def test_all_byte_values(self):
        data = make_bytes(512, "counter")
        self.assertEqual(data[:256], bytes(range(256)))
        self.assertEqual(data[256:], bytes(range(256)))

    def test_constant_fill(self):
        self.assertEqual(make_bytes(17, "constant", value=0xD3), bytes([0xD3]) * 17)

    def test_prng_repeatable(self):
        self.assertEqual(make_bytes(1024, "prng", seed=123),
                         make_bytes(1024, "prng", seed=123))


if __name__ == "__main__":
    unittest.main()
