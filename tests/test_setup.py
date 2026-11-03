"""Exercise portable setup and build behavior using synthetic native data."""
import importlib.util
import json
from pathlib import Path
import plistlib
import runpy
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from native_builder import build_sync, MAC_NAME, IPHONE_NAME
from setup_config import load_setup
from test_cache_image import png


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


builder = module('build_shortcuts')
publication = module('check_publication')
BINDING = {'displayName': 'Example Project', 'filename': 'Example Project',
           'fileLocation': {'WFFileLocationType': 'iCloud', 'relativeSubpath': 'Example Project'}}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='wallpaper-sync-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = (Path(self.temporary.name) / 'A relocated checkout').resolve()
        self.root.mkdir()
        shutil.copy2(ROOT / 'setup.example.json', self.root / 'setup.example.json')
        builder.initialize(self.root)
        self.config = self.root / '.local/setup.json'

    def update(self, **changes):
        value = json.loads(self.config.read_text())
        value.update(changes)
        self.config.write_text(json.dumps(value))

    def ready(self):
        setup = load_setup(root=self.root)
        builder.write_private(setup.folder_binding, plistlib.dumps(BINDING))
        return setup

    def database(self, bindings=(BINDING,), duplicate=False):
        database = self.root / '.local/native-test.sqlite'
        actions = [{'WFWorkflowActionIdentifier': 'is.workflow.actions.documentpicker.open',
                    'WFWorkflowActionParameters': {'WFFile': b}} for b in bindings]
        with sqlite3.connect(database) as connection:
            connection.execute('CREATE TABLE ZSHORTCUT (ZACTIONS INTEGER, ZNAME TEXT, '
                               'ZTOMBSTONED INTEGER, ZWORKFLOWID TEXT)')
            connection.execute('CREATE TABLE ZSHORTCUTACTIONS (Z_PK INTEGER, ZDATA BLOB)')
            connection.execute('INSERT INTO ZSHORTCUTACTIONS VALUES (?,?)',
                               (1, plistlib.dumps(actions)))
            for name in ['Setup', MAC_NAME, IPHONE_NAME] + (['Setup'] if duplicate else []):
                connection.execute('INSERT INTO ZSHORTCUT VALUES (?,?,?,?)', (1, name, 0, 'synthetic-id'))
        return database

    def test_initialization_preserves_existing_settings_and_uses_private_mode(self):
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        before = self.config.read_bytes()
        with self.assertRaisesRegex(ValueError, 'preserved'):
            builder.initialize(self.root)
        self.assertEqual(self.config.read_bytes(), before)

    def test_paths_are_relative_to_checkout_not_working_directory(self):
        setup = self.ready()
        self.assertEqual(setup.folder_binding, self.root / '.local/folder-binding.plist')
        self.assertEqual(setup.output, self.root / 'Shortcuts')
        self.assertEqual(setup.read_binding(), BINDING)

    def test_invalid_schema_platforms_and_paths_are_rejected(self):
        baseline = self.config.read_bytes()
        invalid = [dict(platforms=[]), dict(platforms=['mac', 'mac']), dict(version=True),
                   dict(platforms=['other']), dict(folder_binding='README.md'),
                   dict(folder_binding='../binding.plist'), dict(folder_binding='/tmp/binding.plist'),
                   dict(output='.'), dict(output='src'), dict(output='Shortcuts/../src'),
                   dict(cache_directory='/tmp/Current'), dict(cache_directory='Library/../Current'),
                   dict(cache_directory='Library/Application Support'), dict(extra='unsupported')]
        for changes in invalid:
            with self.subTest(fields=changes):
                self.config.write_bytes(baseline)
                self.update(**changes)
                with self.assertRaises(ValueError):
                    load_setup(root=self.root)

    def test_symlink_escape_from_private_storage_is_rejected(self):
        (self.root / '.local/escape').symlink_to(self.root.parent, target_is_directory=True)
        self.update(folder_binding='.local/escape/native.plist')
        with self.assertRaises(ValueError):
            load_setup(root=self.root)

    def test_capture_deduplicates_binding_without_modifying_native_database(self):
        setup = load_setup(root=self.root)
        database = self.database(bindings=(BINDING, BINDING))
        before = database.read_bytes()
        builder.capture_folder('Setup', setup, database=database)
        self.assertEqual(setup.read_binding(), BINDING)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(setup.folder_binding.stat().st_mode & 0o777, 0o600)
        builder.capture_folder('Setup', setup, database=database)
        builder.record_installation(setup, database=database)
        saved = json.loads((self.root / '.local/install.json').read_text())
        self.assertEqual(set(saved['shortcuts']), {MAC_NAME, IPHONE_NAME})
        self.assertEqual(database.read_bytes(), before)

    def test_capture_rejects_ambiguous_shortcuts_and_folder_references(self):
        setup = load_setup(root=self.root)
        database = self.database(duplicate=True)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            builder.capture_folder('Setup', setup, database=database)
        self.assertFalse(setup.folder_binding.exists())
        database.unlink()
        different = dict(BINDING, filename='Other Project')
        database = self.database(bindings=(BINDING, different))
        with self.assertRaisesRegex(ValueError, 'one project folder'):
            builder.capture_folder('Setup', setup, database=database)
        self.assertFalse(setup.folder_binding.exists())

    def test_private_state_requires_deliberate_replacement(self):
        setup = self.ready()
        before = setup.folder_binding.read_bytes()
        with self.assertRaises(ValueError):
            builder.write_private(setup.folder_binding, b'different')
        self.assertEqual(setup.folder_binding.read_bytes(), before)
        builder.write_private(setup.folder_binding, plistlib.dumps(BINDING, fmt=plistlib.FMT_BINARY), replace=True)
        self.assertEqual(setup.read_binding(), BINDING)

    def test_missing_or_invalid_inputs_do_not_publish_partial_build(self):
        setup = load_setup(root=self.root)
        with self.assertRaises(ValueError):
            builder.build(setup)
        self.assertFalse(setup.output.exists())
        self.ready()
        self.update(iphone_poster='.local/missing.plist')
        with self.assertRaises(ValueError):
            builder.build(load_setup(root=self.root))
        self.assertFalse(setup.output.exists())

    def test_both_platform_builds_preserve_bindings_and_phone_guard(self):
        setup = self.ready()
        self.assertEqual(builder.build(setup), 2)
        for platform, name in [('mac', MAC_NAME), ('iphone', IPHONE_NAME)]:
            value = plistlib.loads((setup.output / (name + '.unsigned.shortcut')).read_bytes())
            self.assertEqual(value['WFWorkflowActions'], build_sync(BINDING, platform).actions)
            self.assertFalse(value['WFWorkflowHasShortcutInputVariables'])
            for action in value['WFWorkflowActions']:
                p = action['WFWorkflowActionParameters']
                if 'WFFile' in p:
                    self.assertEqual(p['WFFile'], BINDING)
            if platform == 'iphone':
                self.assertNotIn('WFSelectedPoster', str(value))
                self.assertIn('setup_required', str(value))
                self.assertNotIn('runshellscript', str(value))
        builder.build(setup, diagnostics=True)
        self.assertEqual(len(list((self.root / '.local/development').glob('*.shortcut'))), 2)

    def test_cache_setting_is_quoted_and_runtime_resolves_home_directory(self):
        cache = "Library/Application Support/Example's $(literal)/Current"
        self.update(cache_directory=cache)
        setup = self.ready()
        shortcut = build_sync(BINDING, cache_directory=setup.cache_directory)
        script = next(a['WFWorkflowActionParameters']['Script'] for a in shortcut.actions
                      if a['WFWorkflowActionIdentifier'].endswith('.runshellscript'))
        command = shlex.split(script.splitlines()[0])
        self.assertEqual(command[command.index('--cache-directory') + 1], cache)
        source = self.root / 'source.png'
        source.write_bytes(png(90))
        with patch('pathlib.Path.home', return_value=self.root), patch.object(
                sys, 'argv', ['cache_image.py', '--cache-directory', cache, str(source)]):
            runpy.run_path(str(ROOT / 'src/cache_image.py'), run_name='__main__')
        self.assertEqual((self.root / cache / 'wallpaper-1.png').read_bytes(), source.read_bytes())

    def test_cli_runs_after_relocation_without_existing_personal_state(self):
        self.ready()
        shutil.copytree(ROOT / 'src', self.root / 'src', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        command = [sys.executable, str(self.root / 'scripts/build_shortcuts.py')]
        for options in [['--check'], []]:
            result = subprocess.run(command + options, cwd=self.root.parent,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertEqual(len(list((self.root / 'Shortcuts').glob('*.shortcut'))), 2)

    def test_publication_check_uses_staged_bytes_and_rejects_private_artifacts(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        source = self.root / 'README.md'
        source.write_text('Portable source\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'README.md'], check=True)
        source.write_text('Different worktree bytes\n')
        count, issues = publication.check_staged(self.root)
        self.assertEqual((count, issues), (1, []))
        private = self.root / '.local/private.txt'
        private.write_text('Private local record\n')
        subprocess.run(['git', '-C', str(self.root), 'add', '.local/private.txt'], check=True)
        self.assertTrue(publication.check_staged(self.root)[1])

    def test_publication_check_reports_sensitive_locations_without_echoing_values(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        source = self.root / 'example.txt'
        source.write_text('/' + 'Users' + '/Example/project\n' +
                          'person' + '@' + 'example.test\n' + 'ghp_' + 'x' * 32 + '\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'example.txt'], check=True)
        count, issues = publication.check_staged(self.root)
        self.assertEqual(count, 1)
        self.assertEqual({reason for _, reason in issues},
                         {'absolute account path', 'provider credential',
                          'Email address needs a publication review'})
        self.assertTrue(all('person' not in reason and 'Example' not in reason
                            and 'x' * 32 not in reason for _, reason in issues))


if __name__ == '__main__':
    unittest.main()
