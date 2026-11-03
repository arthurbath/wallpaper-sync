"""Validate the installed iPhone draft on Mac without applying any wallpaper."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_builder import build_sync
from native_core_test import run
from native_schedule_test import normalized_actions
from selection import day_number, raw_permutation, selection_index
from setup_config import load_setup


def fingerprint():
    cache = load_setup().cache_path
    store = Path.home() / 'Library/Application Support/com.apple.wallpaper/Store/Index.plist'
    return {
        'cache': {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                  for p in sorted(cache.iterdir()) if p.is_file()},
        'settings': hashlib.sha256(store.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shortcut', default='Shuffle Sync Wallpapers (iOS) Development')
    parser.add_argument('--receipt', type=Path)
    options = parser.parse_args()
    before = fingerprint()
    setup = load_setup()
    binding = setup.read_binding()
    database = Path.home() / 'Library/Shortcuts/Shortcuts.sqlite'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute(
            'SELECT s.Z_PK, s.ZWORKFLOWID, a.ZDATA FROM ZSHORTCUT s '
            'JOIN ZSHORTCUTACTIONS a ON s.ZACTIONS=a.Z_PK '
            'WHERE s.ZTOMBSTONED=0 AND (s.ZNAME=? OR s.ZWORKFLOWID=?)',
            (options.shortcut, options.shortcut)).fetchall()
        assert len(rows) == 1, 'Expected one unambiguous installed iPhone draft'
        primary_key, workflow_id, data = rows[0]
        actions = plistlib.loads(data)
        assert normalized_actions(actions) == normalized_actions(build_sync(
            binding, 'iphone', diagnostics=True, cache_directory=setup.cache_directory).actions)
        assert connection.execute('SELECT COUNT(*) FROM ZUNIFIEDTRIGGER WHERE ZSHORTCUT=?',
                                  (primary_key,)).fetchone()[0] == 0, 'Draft must have no active schedule'
    identifiers = [a['WFWorkflowActionIdentifier'] for a in actions]
    assert identifiers.count('is.workflow.actions.wallpaper.set') == 1
    for unsupported in ['runshellscript', 'runapplescript', 'runworkflow', 'ask', 'choosefromlist']:
        assert 'is.workflow.actions.' + unsupported not in identifiers, unsupported
    setter = actions[identifiers.index('is.workflow.actions.wallpaper.set')]['WFWorkflowActionParameters']
    assert setter['WFWallpaperLocation'] == ['Lock Screen', 'Home Screen']
    assert setter['WFWallpaperShowPreview'] is False
    assert setter['WFWallpaperSmartCrop'] is False
    assert 'WFSelectedPoster' not in setter, 'Draft must not claim a phone-specific binding'
    print('PASS installed native draft matches source, with no helpers, scripts, or schedule', flush=True)

    day = day_number('2026-11-01')
    cases = [(n, day) for n in [0, 1, 2, 3, 72, 100]]
    cycle = next(c for c in range(1, 200) if raw_permutation(5, c)[0] == raw_permutation(5, c - 1)[-1])
    cases.extend((5, cycle * 5 + offset) for offset in [-1, 0, 1])
    for count, d in cases:
        actual = run(options.shortcut, {'mode': 'index', 'count': count, 'day': d})
        if not count:
            assert actual == {'status': 'empty', 'count': 0}, actual
        else:
            assert actual['index'] == selection_index(count, d), actual
            assert actual['cycle'] == d // count and actual['position'] == d % count, actual
        print('PASS native iPhone draft index count=%d day=%d' % (count, d), flush=True)

    dates = ['2026-11-01T06:59:59Z', '2026-11-01T07:00:00Z',
             '2026-11-01T09:00:00Z', '2026-03-08T10:00:00Z', '2028-02-29T08:00:00Z']
    for value in dates:
        request = {'mode': 'select', 'as_of': value}
        actual = run(options.shortcut, request)
        mac = run('Shuffle Sync Wallpapers (macOS) Development', request)
        assert actual == mac, (value, actual, mac)
        print('PASS identical Mac/iPhone-draft catalog selection at %s' % value, flush=True)

    today = datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
    decoded = run(options.shortcut, {'as_of': today, 'dry_run': 1})
    assert decoded['status'] == 'validated', decoded
    normal = run(options.shortcut, {'as_of': today})
    assert normal['status'] == 'unsupported_device', normal
    assert normal['filename'] == decoded['filename'], (normal, decoded)
    print('PASS image decoding and normal-run Mac application guard', flush=True)

    with tempfile.TemporaryDirectory(prefix='QA-iPhone-', dir=ROOT) as directory:
        request = {'folder': Path(directory).name, 'as_of': today}
        empty = run(options.shortcut, request)
        assert empty['status'] == 'empty', empty
        (Path(directory) / 'Corrupt.png').write_bytes(b'Not a PNG image')
        for attempt in range(15):
            visible = run(options.shortcut, dict(request, mode='select'))
            if visible.get('filename') == 'Corrupt.png':
                break
            time.sleep(1)
        assert visible.get('filename') == 'Corrupt.png', visible
        try:
            corrupt = run(options.shortcut, request)
        except AssertionError as error:
            # The native decoder may reject corrupt bytes before returning JSON.
            if 'image' not in str(error).lower():
                raise
            corrupt = {'status': 'native_decode_error', 'error': str(error)}
        assert corrupt['status'] in {'invalid_image', 'native_decode_error'}, corrupt
    after = fingerprint()
    assert after == before, 'The draft changed the Mac wallpaper configuration or cache'
    print('PASS empty/corrupt inputs and all draft runs preserve Mac cache and wallpaper settings', flush=True)
    receipt = {'shortcut': options.shortcut, 'workflow_id': workflow_id, 'actions': len(actions),
               'index_cases': len(cases), 'cross_variant_dates': dates, 'validated_selection': decoded,
               'mac_guard': normal['status'], 'empty_guard': empty['status'],
               'corrupt_guard': corrupt['status'], 'mac_state_unchanged': True,
               'iphone_runtime_observed': False, 'automation_count': 0}
    if options.receipt:
        options.receipt.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
