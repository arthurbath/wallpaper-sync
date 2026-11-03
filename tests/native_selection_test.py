"""Check arbitrary image names through installed native Shortcuts, with guarded cleanup."""
import base64
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from selection import select
from native_core_test import run

ROOT = Path(__file__).resolve().parents[1]


def check_catalog(images):
    shortcut = 'Shuffle Sync Wallpapers (macOS) Development'
    created = {}
    directory = images / 'ws-qa folder.png'
    assert not directory.exists()
    payload = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=')

    def create(name, data=payload):
        path = images / name
        with path.open('xb') as stream:
            stream.write(data)
        created[path] = data

    def check(as_of, names):
        expected = select(names, as_of)
        for attempt in range(15):
            actual = run(shortcut, {'as_of': as_of, 'folder': images.name, 'mode': 'select'})
            if actual.get('count') == expected['count']:
                break
            if actual.get('status') not in {'selected', 'empty', 'unavailable'}:
                raise AssertionError(actual)
            time.sleep(1)
        for key, value in expected.items():
            assert actual.get(key) == value, (key, expected, actual)
        print('PASS native catalog count=%d date=%s filename=%r' %
              (len(names), as_of, actual.get('filename')), flush=True)
        return actual.get('filename')

    try:
        create('Fixture.png')
        check('2026-10-31', ['Fixture.png'])
        create('Second fixture.PNG')
        check('2026-10-31', ['Fixture.png', 'Second fixture.PNG'])
        check('2026-11-01', ['Fixture.png', 'Second fixture.PNG'])
        second = images / 'Second fixture.PNG'
        second.unlink()
        created.pop(second)
        image_names = ["ws-qa A summer's day.JPG", 'ws-qa café 🍁.PNG',
                       'ws-qa quote " one.png', 'ws-qa same.jpg', 'ws-qa same.png',
                       'ws-qa Photo 2.PNG', 'ws-qa Photo 02.png', 'ws-qa 日本語.heic',
                       'ws-qa line\nbreak.png']
        for name in image_names:
            create(name)
        create('ws-qa notes.txt', b'Not an image')
        directory.mkdir()
        names = ['Fixture.png'] + image_names
        selected = []
        start = date(2026, 10, 31)
        for offset in range(len(names) * 2 + 1):
            selected.append(check((start + timedelta(days=offset)).isoformat(), names))
        assert all(a != b for a, b in zip(selected, selected[1:])), selected
        for timestamp in ['2026-11-01T06:59:59Z', '2026-11-01T07:00:00Z',
                          '2026-11-01T09:00:00Z', '2026-03-08T10:00:00Z',
                          '2028-02-29T08:00:00Z', '2026-11-01T16:00:00+09:00']:
            check(timestamp, names)
        for path, content in created.items():
            assert path.read_bytes() == content
            path.unlink()
        for path, content in reversed(list(created.items())):
            with path.open('xb') as stream:
                stream.write(content)
        check('2026-10-31', names)
        renamed = "ws-qa Renamed beach.JPG"
        path = images / image_names[0]
        new_path = images / renamed
        assert not new_path.exists()
        path.rename(new_path)
        created[new_path] = created.pop(path)
        names.remove(image_names[0])
        names.append(renamed)
        check('2026-10-31', names)
        removed = images / image_names[1]
        assert removed.read_bytes() == created[removed]
        removed.unlink()
        created.pop(removed)
        names.remove(image_names[1])
        check('2026-10-31', names)
    finally:
        for path, content in created.items():
            if path.exists() and path.read_bytes() == content:
                path.unlink()
        if directory.exists():
            directory.rmdir()
    check('2026-10-31', [])
    print('PASS isolated catalog cleaned', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='QA-Catalog-', dir=ROOT) as directory:
        check_catalog(Path(directory))


if __name__ == '__main__':
    main()
