"""Validate local setup without putting native device references in source."""
from dataclasses import dataclass
import json
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETUP = '.local/setup.json'


class SetupError(ValueError):
    """An actionable validation message that contains no private input values."""


def local_path(root, value, allowed, label):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) < 32 for c in value):
        raise SetupError('%s must be a repository-relative path' % label)
    relative = Path(value)
    if (not relative.parts or relative.is_absolute() or '..' in relative.parts
            or relative.parts[0] not in allowed):
        raise SetupError('%s must stay inside ignored local storage' % label)
    result = (root / relative).resolve()
    if root not in result.parents:
        raise SetupError('%s must stay inside the repository' % label)
    base = root / relative.parts[0]
    if result != base and base not in result.parents:
        raise SetupError('%s must stay inside ignored local storage' % label)
    return result


def validate_binding(value):
    if (not isinstance(value, dict) or not isinstance(value.get('fileLocation'), dict)
            or not isinstance(value['fileLocation'].get('WFFileLocationType'), str)
            or not isinstance(value.get('filename'), str) or not value['filename']):
        raise SetupError('Folder binding must be a native folder reference captured from Shortcuts')
    return value


@dataclass(frozen=True)
class Setup:
    root: Path
    platforms: tuple
    folder_binding: Path
    iphone_poster: object
    output: Path
    cache_directory: str

    @property
    def cache_path(self):
        return Path.home() / self.cache_directory

    def read_binding(self):
        try:
            return validate_binding(plistlib.loads(self.folder_binding.read_bytes()))
        except FileNotFoundError:
            raise SetupError('Capture a folder reference with --capture-folder before building') from None
        except plistlib.InvalidFileException:
            raise SetupError('Folder binding is not a valid plist') from None

    def read_poster(self):
        if self.iphone_poster is None:
            return None
        try:
            value = plistlib.loads(self.iphone_poster.read_bytes())
        except (FileNotFoundError, plistlib.InvalidFileException):
            raise SetupError('The configured iPhone poster must be an existing native plist') from None
        if not isinstance(value, dict) or not value:
            raise SetupError('The configured iPhone poster must be a nonempty native dictionary')
        return value


def load_setup(path=DEFAULT_SETUP, root=ROOT):
    root = Path(root).resolve()
    source = local_path(root, str(path), {'.local'}, 'Setup file')
    try:
        value = json.loads(source.read_text())
    except FileNotFoundError:
        raise SetupError('Local setup is missing. Run scripts/build_shortcuts.py --init first') from None
    except json.JSONDecodeError:
        raise SetupError('Local setup must contain valid JSON') from None
    keys = {'version', 'platforms', 'folder_binding', 'iphone_poster', 'output', 'cache_directory'}
    if not isinstance(value, dict) or set(value) != keys:
        raise SetupError('Setup must contain exactly the fields in setup.example.json')
    if type(value['version']) is not int or value['version'] != 1:
        raise SetupError('Unsupported setup version')
    platforms = value['platforms']
    if (not isinstance(platforms, list) or not platforms
            or any(p not in ('mac', 'iphone') for p in platforms)
            or len(set(platforms)) != len(platforms)):
        raise SetupError('Platforms must contain unique mac and/or iphone entries')
    cache = value['cache_directory']
    if (not isinstance(cache, str) or not cache or '\\' in cache or any(ord(c) < 32 for c in cache)
            or Path(cache).is_absolute() or '..' in Path(cache).parts
            or Path(cache).parts[:2] != ('Library', 'Application Support')
            or len(Path(cache).parts) < 4):
        raise SetupError('Cache directory must name a subfolder under Library/Application Support')
    binding = local_path(root, value['folder_binding'], {'.local'}, 'Folder binding')
    poster = (None if value['iphone_poster'] is None else
              local_path(root, value['iphone_poster'], {'.local'}, 'iPhone poster'))
    output = local_path(root, value['output'], {'.local', 'Shortcuts'}, 'Output')
    if binding == source or poster == source or binding == poster:
        raise SetupError('Setup and native binding files must use separate paths')
    return Setup(root, tuple(platforms), binding, poster, output, cache)
