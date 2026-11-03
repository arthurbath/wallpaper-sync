"""Initialize private setup, capture native references, and build local exports."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_builder import build_sync, MAC_NAME, IPHONE_NAME
from setup_config import DEFAULT_SETUP, load_setup, local_path, validate_binding, SetupError


def write_private(path, data, replace=False):
    """Save private state without clobbering an existing setup by default."""
    path = Path(path)
    if path.is_symlink():
        raise SetupError('Private state files must not be symlinks')
    if path.exists():
        if path.read_bytes() == data:
            return False
        if not replace:
            raise SetupError('Local state already exists. Use --replace only to replace it deliberately')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.setup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Linking a complete temporary file provides exclusive creation.
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def initialize(root=ROOT, setup_path=DEFAULT_SETUP):
    root = Path(root).resolve()
    destination = local_path(root, setup_path, {'.local'}, 'Setup file')
    if destination.exists():
        raise SetupError('Local setup already exists and was preserved')
    write_private(destination, (root / 'setup.example.json').read_bytes())


def native_connection(database=None):
    path = (Path(database) if database is not None else
            Path.home() / 'Library/Shortcuts/Shortcuts.sqlite')
    if not path.is_file():
        raise SetupError('Shortcuts database is unavailable. Create the setup shortcut first')
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def capture_folder(shortcut_name, setup, replace=False, database=None):
    with native_connection(database) as connection:
        rows = connection.execute(
            'SELECT a.ZDATA FROM ZSHORTCUT s JOIN ZSHORTCUTACTIONS a ON s.ZACTIONS=a.Z_PK '
            'WHERE s.ZTOMBSTONED=0 AND s.ZNAME=?', (shortcut_name,)).fetchall()
    if len(rows) != 1:
        raise SetupError('Expected exactly one saved setup shortcut with that name')
    actions = plistlib.loads(rows[0][0])
    if not isinstance(actions, list) or any(not isinstance(a, dict) for a in actions):
        raise SetupError('The saved shortcut does not contain a supported native action list')
    bindings = []
    for action in actions:
        if action.get('WFWorkflowActionIdentifier') != 'is.workflow.actions.documentpicker.open':
            continue
        binding = action.get('WFWorkflowActionParameters', {}).get('WFFile')
        if isinstance(binding, dict) and isinstance(binding.get('fileLocation'), dict):
            validate_binding(binding)
            if binding not in bindings:
                bindings.append(binding)
    if len(bindings) != 1:
        raise SetupError('Select one project folder in Get File from Folder, save, and try again')
    write_private(setup.folder_binding, plistlib.dumps(bindings[0]), replace=replace)


def record_installation(setup, replace=False, database=None):
    installed = {}
    with native_connection(database) as connection:
        for platform in setup.platforms:
            name = MAC_NAME if platform == 'mac' else IPHONE_NAME
            rows = connection.execute(
                'SELECT ZWORKFLOWID FROM ZSHORTCUT WHERE ZTOMBSTONED=0 AND ZNAME=?',
                (name,)).fetchall()
            if len(rows) != 1:
                raise SetupError('Each configured shortcut must have one unambiguous local installation')
            installed[name] = rows[0][0]
    payload = json.dumps({'shortcuts': installed}, indent=2).encode() + b'\n'
    write_private(setup.root / '.local/install.json', payload, replace=replace)


def build(setup, diagnostics=False, sign=False):
    binding, poster = setup.read_binding(), setup.read_poster()
    output = (local_path(setup.root, '.local/development', {'.local'}, 'Output')
              if diagnostics else setup.output)
    shortcuts = []
    for platform in setup.platforms:
        shortcut = build_sync(binding, platform, poster if platform == 'iphone' else None,
                              diagnostics=diagnostics, cache_directory=setup.cache_directory)
        if diagnostics:
            shortcut.name += ' Development'
        shortcuts.append(shortcut)
    output.mkdir(parents=True, exist_ok=True)
    for shortcut in shortcuts:
        unsigned = output / (shortcut.name + '.unsigned.shortcut')
        shortcut.write(unsigned)
        if sign:
            signed = output / (shortcut.name + '.shortcut')
            subprocess.run(['/usr/bin/shortcuts', 'sign', '--mode', 'anyone',
                            '--input', str(unsigned), '--output', str(signed)], check=True,
                           capture_output=True, timeout=120)
    return len(shortcuts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', default=DEFAULT_SETUP,
                        help='Configuration path under .local, relative to the repository')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--init', action='store_true', help='Copy setup.example.json into private storage')
    mode.add_argument('--capture-folder', metavar='SHORTCUT', help='Read the folder selected in a saved shortcut')
    mode.add_argument('--record-installation', action='store_true', help='Save discovered local shortcut IDs')
    mode.add_argument('--check', action='store_true', help='Validate setup and native inputs without building')
    parser.add_argument('--replace', action='store_true', help='Allow replacing captured or recorded local state')
    parser.add_argument('--diagnostics', action='store_true', help='Build separate development exports under .local')
    parser.add_argument('--sign', action='store_true', help='Send generated exports to Apple for signing')
    options = parser.parse_args()
    if options.replace and not (options.capture_folder or options.record_installation):
        parser.error('--replace requires --capture-folder or --record-installation')
    if (options.sign or options.diagnostics) and (options.init or options.capture_folder
                                                or options.record_installation or options.check):
        parser.error('--sign and --diagnostics apply only to builds')
    try:
        if options.init:
            initialize(setup_path=options.setup)
            print('Created private setup. Edit it before capturing your project folder.')
            return
        setup = load_setup(options.setup)
        if options.capture_folder:
            capture_folder(options.capture_folder, setup, options.replace)
            print('Saved the folder reference in ignored local storage.')
        elif options.record_installation:
            record_installation(setup, options.replace)
            print('Saved installation identifiers in ignored local storage.')
        elif options.check:
            setup.read_binding()
            setup.read_poster()
            print('Local setup and native inputs are valid.')
        else:
            count = build(setup, options.diagnostics, options.sign)
            print('Built %d shortcut export(s) in ignored output storage.' % count)
    except (ValueError, OSError, sqlite3.Error, plistlib.InvalidFileException,
            subprocess.SubprocessError):
        # Configuration/native objects may carry account IDs or personal paths.
        # Report useful validation messages without echoing their payloads.
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, SetupError) else 'Local operation failed. Check file access and setup.'
        parser.exit(2, 'Setup error: ' + message + '\n')


if __name__ == '__main__':
    main()
