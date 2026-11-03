"""Prepare identical, fixed-name images for macOS's native shared folder rotation.

Embedded in the shortcut. No wallpaper API, UI, or process control runs here.
"""
import fcntl
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import zlib

CACHE_NAMES = ('wallpaper-1.png', 'wallpaper-2.png')
DEFAULT_CACHE_DIRECTORY = 'Library/Application Support/Wallpaper Sync/Current'


def validate_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Expected the decoded PNG from Shortcuts')
    offset, first, ended = 8, True, False
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG')
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError('Invalid PNG checksum')
        if first:
            if kind != b'IHDR' or length != 13 or not all(struct.unpack('>II', payload[:8])):
                raise ValueError('Invalid PNG dimensions')
            first = False
        if kind == b'IEND':
            ended = length == 0 and end == len(data)
            break
        offset = end
    if not ended:
        raise ValueError('Incomplete PNG')


def prepare(source, directory):
    data = Path(source).read_bytes()
    validate_png(data)
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Cache folder must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).digest()
    with (directory.parent / '.write.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        staged = []
        try:
            for name in CACHE_NAMES:
                target = directory / name
                if target.is_symlink():
                    raise ValueError('Cache image must not be a symlink')
                if target.is_file() and hashlib.sha256(target.read_bytes()).digest() == digest:
                    continue
                fd, temporary = tempfile.mkstemp(prefix='.wallpaper-', suffix='.tmp',
                                                 dir=directory.parent)
                staged.append((Path(temporary), target))
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(temporary, 0o644)
            # All replacements are fully written before the first visible change.
            for temporary, target in staged:
                os.replace(temporary, target)
            return bool(staged)
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-directory', default=DEFAULT_CACHE_DIRECTORY)
    parser.add_argument('source', type=Path)
    options = parser.parse_args()
    relative = Path(options.cache_directory)
    if relative.is_absolute() or '..' in relative.parts or len(relative.parts) < 2:
        parser.error('--cache-directory must be a relative directory under the home folder')
    prepare(options.source, Path.home() / relative)
