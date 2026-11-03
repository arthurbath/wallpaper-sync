"""Check background cache publication, retention, and repeated execution."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cache_image import prepare


def png(red):
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes([0, red, 0, 0]))) + chunk(b'IEND', b''))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.png'
        self.source.write_bytes(png(25))
        self.cache = self.root / 'Current'

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.cache.iterdir()}

    def test_two_identical_copies_and_idempotence(self):
        self.assertTrue(prepare(self.source, self.cache))
        self.assertEqual(set(p.name for p in self.cache.iterdir()), {'wallpaper-1.png', 'wallpaper-2.png'})
        self.assertTrue(all(p.read_bytes() == self.source.read_bytes() for p in self.cache.iterdir()))
        before = self.snapshot()
        self.assertFalse(prepare(self.source, self.cache))
        self.assertEqual(self.snapshot(), before)
        self.source.write_bytes(png(200))
        self.assertTrue(prepare(self.source, self.cache))
        self.assertTrue(all(p.read_bytes() == png(200) for p in self.cache.iterdir()))

    def test_missing_truncated_and_corrupt_inputs_preserve_cache(self):
        prepare(self.source, self.cache)
        before = self.snapshot()
        for invalid in [b'not an image', png(80)[:-1], png(80)[:40] + b'x' + png(80)[41:]]:
            self.source.write_bytes(invalid)
            with self.assertRaises(ValueError):
                prepare(self.source, self.cache)
            self.assertEqual(self.snapshot(), before)
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            prepare(self.source, self.cache)
        self.assertEqual(self.snapshot(), before)

    def test_staging_failure_publishes_nothing(self):
        prepare(self.source, self.cache)
        before = self.snapshot()
        self.source.write_bytes(png(220))
        with patch('cache_image.os.fsync', side_effect=OSError('Injected write failure')):
            with self.assertRaises(OSError):
                prepare(self.source, self.cache)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.root.glob('.wallpaper-*.tmp')), [])

    def test_cache_does_not_follow_symlinks(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        self.cache.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare(self.source, self.cache)
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
