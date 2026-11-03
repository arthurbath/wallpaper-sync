"""Reference implementation for the native Wallpaper Sync shortcuts."""
import hashlib
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo('America/Los_Angeles')
EPOCH = date(1970, 1, 1)
MODULUS = 2147483647
MULTIPLIER = 48271


def canonical_names(names):
    """Order already identified image filenames independently of device collation."""
    keyed = [(hashlib.sha256(name.encode('utf-8')).hexdigest(), name) for name in names]
    if len({key for key, _ in keyed}) != len(keyed):
        raise ValueError('Image filenames and their ordering keys must be unique')
    return [name for _, name in sorted(keyed)]


def day_number(as_of=None):
    if as_of is None:
        day = datetime.now(PACIFIC).date()
    elif isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            raise ValueError('Timestamps require an explicit time zone')
        day = as_of.astimezone(PACIFIC).date()
    elif isinstance(as_of, date):
        day = as_of
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', as_of):
        day = date.fromisoformat(as_of)
    else:
        moment = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            raise ValueError('Timestamps require an explicit time zone')
        day = moment.astimezone(PACIFIC).date()
    return (day - EPOCH).days


def raw_permutation(count, cycle):
    state = 1 + ((104729 + cycle) % (MODULUS - 1))
    for _ in range(5):
        state = (MULTIPLIER * state) % MODULUS
    result = list(range(count))
    for index in range(count - 1, 0, -1):
        state = (MULTIPLIER * state) % MODULUS
        other = state % (index + 1)
        result[index], result[other] = result[other], result[index]
    return result


def selection_index(count, day):
    if count < 0 or day < 0 or not isinstance(count, int) or not isinstance(day, int):
        raise ValueError('Count and day must be nonnegative integers')
    if not count:
        return None
    if count == 1:
        return 0
    if count == 2:
        return day % 2
    cycle, position = divmod(day, count)
    permutation = raw_permutation(count, cycle)
    if permutation[0] == raw_permutation(count, cycle - 1)[-1]:
        permutation[0], permutation[1] = permutation[1], permutation[0]
    return permutation[position]


def select(names, as_of=None):
    names = canonical_names(names)
    day = day_number(as_of)
    index = selection_index(len(names), day)
    if index is None:
        return {'status': 'empty', 'count': 0}
    cycle, position = divmod(day, len(names))
    return {'status': 'selected', 'count': len(names), 'day': day,
            'cycle': cycle, 'position': position, 'index': index, 'filename': names[index]}
