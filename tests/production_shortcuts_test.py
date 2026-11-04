"""Verify installed production artifacts, native scheduling, and background execution."""
import argparse
import json
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_builder import build_sync, ICON, IPHONE_NAME, MAC_NAME
from native_schedule_test import normalized_actions, NOTIFICATION_OFF
from iphone_draft_test import fingerprint
from setup_config import load_setup


def run(shortcut):
    with tempfile.TemporaryDirectory(prefix='wallpaper-sync-production-') as directory:
        output = Path(directory) / 'result.json'
        result = subprocess.run(['/usr/bin/shortcuts', 'run', shortcut, '-o', str(output),
            '--output-type', 'public.plain-text'], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        return json.loads(output.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path)
    options = parser.parse_args()
    setup = load_setup()
    binding = setup.read_binding()
    database = Path.home() / 'Library/Shortcuts/Shortcuts.sqlite'
    installed = {}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        for platform, name in [('mac', MAC_NAME), ('iphone', IPHONE_NAME)]:
            rows = connection.execute(
                'SELECT s.Z_PK,s.ZWORKFLOWID,s.ZDISABLEDONLOCKSCREEN,a.ZDATA,'
                'i.ZGLYPHNUMBER,i.ZBACKGROUNDCOLORVALUE FROM ZSHORTCUT s '
                'JOIN ZSHORTCUTACTIONS a ON s.ZACTIONS=a.Z_PK '
                'JOIN ZSHORTCUTICON i ON s.ZICON=i.Z_PK '
                'WHERE s.ZTOMBSTONED=0 AND s.ZNAME=?', (name,)).fetchall()
            assert len(rows) == 1, (name, len(rows))
            primary_key, workflow_id, locked, data, glyph, color = rows[0]
            actions = plistlib.loads(data)
            assert normalized_actions(actions) == normalized_actions(build_sync(
                binding, platform, cache_directory=setup.cache_directory).actions)
            assert (glyph, color) == (ICON['WFWorkflowIconGlyphNumber'], ICON['WFWorkflowIconStartColor'])
            assert locked == 0, name
            assert 'draft' not in json.dumps(actions).lower()
            assert 'ExtensionInput' not in json.dumps(actions), 'Production still processes test input'
            triggers = connection.execute(
                'SELECT ZENABLEMENT,ZNOTIFICATIONLEVEL,ZDATA FROM ZUNIFIEDTRIGGER '
                'WHERE ZSHORTCUT=?', (primary_key,)).fetchall()
            if platform == 'mac':
                assert len(triggers) == 24
                times = []
                for enabled, level, blob in triggers:
                    assert enabled == 1
                    assert level == NOTIFICATION_OFF, 'A Mac trigger is not set to Notify off'
                    trigger = plistlib.loads(blob)
                    assert trigger['WFTriggerIdentifier'] == 'WFTimeOfDayTrigger'
                    components = trigger['WFTriggerSerializedParameters']['WFTimeComponents']
                    times.append((components['hour'], components['minute']))
                assert sorted(times) == [(hour, 0) for hour in range(24)]
            else:
                assert not triggers, 'The Mac iOS validation copy must remain unscheduled'
            installed[name] = {'workflow_id': workflow_id, 'actions': len(actions),
                'triggers': len(triggers), 'notification_levels': sorted(set(t[1] for t in triggers))}
            print('PASS installed production name, icon, bindings, and schedule:', name, flush=True)

    settings = fingerprint()['settings']
    assert run(MAC_NAME) in ({'status': 'prepared'}, {'status': 'already_completed'})
    before = fingerprint()
    assert before['settings'] == settings, 'Mac run modified native wallpaper settings'
    assert run(MAC_NAME) == {'status': 'already_completed'}
    assert fingerprint() == before, 'Repeated Mac run modified wallpaper settings or cache'
    assert run(IPHONE_NAME) == {'status': 'unsupported_device'}
    assert fingerprint() == before, 'The iOS build modified Mac wallpaper state'
    print('PASS production Mac daily completion and repeat skip; iOS decoding and Mac guard', flush=True)
    if options.receipt:
        options.receipt.write_text(json.dumps({'installed': installed, 'icon': ICON,
            'mac_application': 'prepared_or_already_completed', 'repeat_daily_skip': True,
            'mac_settings_unchanged': True, 'ios_mac_guard': 'unsupported_device',
            'final_ios_runtime_observed': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
