"""Compare full native filenames across the Mac and iPhone shortcut variants."""
import argparse
import base64
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from iphone_draft_test import fingerprint
from native_core_test import run
from selection import select


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shortcut', default='Shuffle Sync Wallpapers (iOS) Development')
    parser.add_argument('--receipt', type=Path)
    options = parser.parse_args()
    names = ['Coast.png', 'Coast.JPG', 'repeat.png.png', 'café 🍁.HEIC']
    payload = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=')
    before = fingerprint()
    selected = []
    with tempfile.TemporaryDirectory(prefix='QA-Filename-', dir=ROOT) as directory:
        folder = Path(directory)
        for name in names:
            (folder / name).write_bytes(payload)
        # Start at a four-image cycle boundary so every original name is selected.
        for offset in range(4):
            as_of = (date(2026, 11, 3) + timedelta(days=offset)).isoformat()
            request = {'folder': folder.name, 'as_of': as_of, 'mode': 'select'}
            for attempt in range(15):
                actual = run(options.shortcut, request)
                if actual.get('count') == len(names):
                    break
                time.sleep(1)
            mac = run('Shuffle Sync Wallpapers (macOS) Development', request)
            expected = select(names, as_of)
            assert actual == mac, (actual, mac)
            for key, value in expected.items():
                assert actual.get(key) == value, (actual, expected)
            selected.append(actual['filename'])
            print('PASS exact native filename %r' % actual['filename'], flush=True)
    assert set(selected) == set(names), selected
    assert fingerprint() == before, 'Selection diagnostics changed the Mac wallpaper state'
    print('PASS original extension case, repeated extensions, Unicode, and same-base names', flush=True)
    if options.receipt:
        options.receipt.write_text(json.dumps({'filenames': selected, 'mac_match': True,
            'reference_match': True, 'mac_state_unchanged': True,
            'iphone_runtime_observed': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
