"""Check the exact staged source snapshot before making it public."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SUFFIXES = {'.shortcut', '.plist', '.log', '.pem', '.key', '.p12', '.pfx',
                    '.png', '.jpg', '.jpeg', '.heic', '.gif', '.sqlite', '.db'}
PATTERNS = {
    'absolute account path': re.compile(
        r'/(?:Us' + r'ers|ho' + r'me)/[^/\s\x22\x27]+/|[A-Za-z]:\\Us' + r'ers\\'),
    'private key': re.compile(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----'),
    'provider credential': re.compile(
        r'(?<![A-Za-z0-9])(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}'
        r'|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'
        r'|(?:AKIA|ASIA)[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,}'
        r'|AIza[A-Za-z0-9_-]{30,})'),
    'JWT': re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    'credential URL': re.compile(r'[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:<>]+:[^\s/@<>]+@'),
}
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def check_staged(root=ROOT):
    entries = git(root, 'ls-files', '--stage', '-z').split(b'\0')
    issues, count = [], 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        path = raw_path.decode()
        count += 1
        item = PurePosixPath(path)
        if stage != '0' or mode not in {'100644', '100755'}:
            issues.append((path, 'Unmerged, linked, or nonregular source entry'))
            continue
        if (any(p in {'.local', '.codex', '.agents', '.aws'} for p in item.parts)
                or any(p.startswith('QA-') for p in item.parts)
                or (item.parts[0] in {'Images', 'Shortcuts'} and item.name != '.gitkeep')
                or item.suffix.lower() in PRIVATE_SUFFIXES
                or item.name in {'setup.json', 'setup.local.json'}
                or (item.name.startswith('.env') and item.name != '.env.example')):
            issues.append((path, 'Private or generated artifact is staged'))
            continue
        raw = git(root, 'cat-file', 'blob', oid)
        try:
            body = raw.decode('utf-8')
        except UnicodeDecodeError:
            issues.append((path, 'Binary content needs a separate publication review'))
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(body):
                line = body[:match.start()].count('\n') + 1
                issues.append((path + ':' + str(line), label))
        for match in EMAIL.finditer(body):
            domain = match.group(1).lower()
            if domain not in {'example.com', 'example.org', 'example.invalid'} and not domain.endswith('.invalid'):
                line = body[:match.start()].count('\n') + 1
                issues.append((path + ':' + str(line), 'Email address needs a publication review'))
    return count, issues


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        count, issues = check_staged()
    except (OSError, subprocess.SubprocessError):
        raise SystemExit('Unable to inspect the staged Git snapshot') from None
    for path, reason in issues:
        print('%s: %s' % (path, reason), file=sys.stderr)
    if issues or not count:
        raise SystemExit(1)
    print('PASS %d staged source files: no recognized private artifacts or sensitive patterns' % count)
    print('This check supplements review. It does not audit previous commits or prove all content is public-safe.')


if __name__ == '__main__':
    main()
