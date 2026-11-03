import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

"""Compare the installed native shortcut with independent Python vectors."""
import json
import subprocess
import tempfile
import time
from pathlib import Path

from selection import day_number, raw_permutation, selection_index


def run(shortcut, value):
    with tempfile.TemporaryDirectory(prefix='wallpaper-sync-qa-') as folder:
        request = Path(folder) / 'input.json'
        response = Path(folder) / 'output.json'
        request.write_text(json.dumps(value))
        result = subprocess.run(['/usr/bin/shortcuts', 'run', shortcut, '-i', str(request),
                                 '-o', str(response), '--output-type', 'public.plain-text'],
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise AssertionError(result.stderr.strip())
        return json.loads(response.read_text())


def main():
    day = day_number('2026-10-31')
    cases = [(n, day) for n in [0, 1, 2, 3, 5, 10, 31, 100, 1000]]
    for n in [3, 5, 10, 31]:
        c = next(c for c in range(1, 200)
                 if raw_permutation(n, c)[0] == raw_permutation(n, c - 1)[-1])
        cases.extend([(n, c * n - 1), (n, c * n), (n, c * n + 1)])
    started = time.monotonic()
    for n, d in cases:
        result = run('Shuffle Sync Wallpapers (macOS) Development', {'mode': 'index', 'count': n, 'day': d})
        if not n:
            assert result == {'status': 'empty', 'count': 0}, result
        else:
            assert result['index'] == selection_index(n, d), (n, d, result)
            assert result['cycle'] == d // n, (n, d, result)
            assert result['position'] == d % n, (n, d, result)
        print('PASS count=%d day=%d' % (n, d), flush=True)
    print('Native vectors passed: %d in %.1fs' % (len(cases), time.monotonic() - started))


if __name__ == '__main__':
    main()
