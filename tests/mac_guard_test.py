import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

"""Verify invalid image input cannot reach the wallpaper setter."""
import hashlib
from pathlib import Path
import sys
import time

from native_core_test import run

ROOT = Path(__file__).resolve().parents[1]
from setup_config import load_setup
SETTINGS = Path.home() / 'Library/Application Support/com.apple.wallpaper/Store/Index.plist'


def settled_settings_hash():
    # The wallpaper service persists successful changes asynchronously.
    previous, stable = None, 0
    for attempt in range(30):
        current = hashlib.sha256(SETTINGS.read_bytes()).hexdigest()
        stable = stable + 1 if current == previous else 0
        if stable >= 4:
            return current
        previous = current
        time.sleep(0.5)
    raise AssertionError('Wallpaper settings did not settle before comparison')


def main():
    import tempfile
    with tempfile.TemporaryDirectory(prefix='QA-Guard-', dir=ROOT) as directory:
        folder = Path(directory)
        arguments = {'folder': folder.name}
        before = settled_settings_hash()
        cache = load_setup().cache_path
        def cache_snapshot():
            return {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                    for p in cache.glob('*.png')}
        cache_before = cache_snapshot()
        result = run('Shuffle Sync Wallpapers (macOS) Development', arguments)
        assert result.get('status') == 'empty' and result.get('count') == 0, result
        print('PASS empty catalog preserves wallpaper', flush=True)
        bad = folder / 'Invalid picture QA.PNG'
        bad.write_bytes(b'This is an intentionally invalid image for Wallpaper Sync QA.\n')
        for attempt in range(15):
            selected = run('Shuffle Sync Wallpapers (macOS) Development', dict(arguments, mode='select'))
            if selected.get('filename') == bad.name:
                break
            time.sleep(1)
        assert selected.get('filename') == bad.name, selected
        try:
            result = run('Shuffle Sync Wallpapers (macOS) Development', arguments)
        except AssertionError as error:
            if 'image' not in str(error).lower():
                raise
            print('PASS native decoder rejected corrupt data', flush=True)
        else:
            assert result.get('status') == 'invalid_image', result
            print('PASS corrupt image rejected', flush=True)
        assert settled_settings_hash() == before, 'Wallpaper settings changed'
        assert cache_snapshot() == cache_before, 'Wallpaper cache changed'
        print('PASS wallpaper settings and cache unchanged', flush=True)


if __name__ == '__main__':
    main()
