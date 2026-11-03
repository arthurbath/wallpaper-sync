"""Inspect the installed native hourly schedule without changing Shortcuts data."""
from pathlib import Path
import plistlib
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_builder import build_sync, MAC_NAME
from setup_config import load_setup

# macOS 27 native trigger UI: Notify off corresponds to stored level 1.
NOTIFICATION_OFF = 1


def normalized(value):
    if isinstance(value, dict):
        if value.get('WFSerializationType') == 'WFTextTokenString':
            token = value['Value']
            attachments = token.get('attachmentsByRange', {})
            if not attachments:
                return token['string']
            if token['string'] == '\ufffc' and set(attachments) == {'{0, 1}'}:
                return normalized({'WFSerializationType': 'WFTextTokenAttachment',
                                   'Value': attachments['{0, 1}']})
        return {key: normalized(item) for key, item in value.items()
                if key != 'OutputName'}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def normalized_actions(actions):
    """Allow native copy/paste UUID renewal while checking every binding and parameter."""
    identifiers = {}
    for action in actions:
        parameters = action['WFWorkflowActionParameters']
        for key in ['UUID', 'GroupingIdentifier']:
            value = parameters.get(key)
            if value and value not in identifiers:
                identifiers[value] = 'identifier-%d' % len(identifiers)

    def remap(value):
        if isinstance(value, str):
            return identifiers.get(value, value)
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        return value

    return normalized(remap(actions))


def main():
    setup = load_setup()
    database = Path.home() / 'Library/Shortcuts/Shortcuts.sqlite'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute(
            'SELECT Z_PK, ZNAME, ZDISABLEDONLOCKSCREEN FROM ZSHORTCUT '
            'WHERE ZTOMBSTONED = 0 AND ZNAME = ?', (MAC_NAME,)).fetchall()
        assert len(rows) == 1, rows
        assert connection.execute(
            'SELECT COUNT(*) FROM ZSHORTCUT WHERE ZTOMBSTONED = 0 AND ZNAME = ?',
            (MAC_NAME,)).fetchone()[0] == 1, 'The shortcut name is ambiguous'
        primary_key, name, disabled_when_locked = rows[0]
        assert name == MAC_NAME, name
        assert disabled_when_locked == 0, 'Locked execution is disabled'
        triggers = connection.execute(
            'SELECT ZENABLEMENT, ZNOTIFICATIONLEVEL, ZDATA FROM ZUNIFIEDTRIGGER '
            'WHERE ZSHORTCUT = ?', (primary_key,)).fetchall()
        assert len(triggers) == 24, 'Expected 24 triggers, found %d' % len(triggers)
        times = []
        for enabled, notification_level, data in triggers:
            assert enabled == 1, 'A trigger is disabled'
            assert notification_level == NOTIFICATION_OFF, 'A trigger does not have verified Notify-off setting'
            trigger = plistlib.loads(data)
            assert trigger['WFTriggerIdentifier'] == 'WFTimeOfDayTrigger', trigger
            parameters = trigger['WFTriggerSerializedParameters']
            time = parameters['WFTimeComponents']
            times.append((time['hour'], time['minute']))
            # An omitted recurrence uses the native Every Day default.
            recurrence = parameters.get('WFRecurrence')
            if recurrence:
                assert recurrence['frequency'] == 3, recurrence
                assert recurrence['interval'] == 1, recurrence
                for key in ['hours', 'minutes', 'seconds', 'weekdays', 'weeks',
                            'daysOfTheMonth', 'daysOfTheYear', 'months', 'setPositions']:
                    assert not recurrence.get(key), (key, recurrence)
        assert sorted(times) == [(hour, 0) for hour in range(24)], sorted(times)
        actions = plistlib.loads(connection.execute(
            'SELECT a.ZDATA FROM ZSHORTCUT s JOIN ZSHORTCUTACTIONS a ON s.ZACTIONS = a.Z_PK '
            'WHERE s.Z_PK = ?', (primary_key,)).fetchone()[0])
    binding = setup.read_binding()
    assert normalized_actions(actions) == normalized_actions(build_sync(
        binding, cache_directory=setup.cache_directory).actions), 'Native actions differ from source'
    assert not any(action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.runworkflow'
                   for action in actions), 'A helper shortcut was introduced'
    print('PASS 24 enabled daily native triggers cover every hour at minute 00')
    print('PASS notifications disabled and running when locked allowed')
    identifiers = [a['WFWorkflowActionIdentifier'] for a in actions]
    assert identifiers.count('is.workflow.actions.runshellscript') == 1
    assert 'is.workflow.actions.wallpaper.set' not in identifiers
    assert 'is.workflow.actions.runapplescript' not in identifiers
    print('PASS actions match source, with one background writer and no helper shortcuts or GUI scripts')


if __name__ == '__main__':
    main()
