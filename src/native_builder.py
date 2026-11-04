"""Build reproducible native Apple Shortcuts without changing its database."""
import plistlib
import shlex
import uuid
from pathlib import Path

from cache_image import DEFAULT_CACHE_DIRECTORY

NAMESPACE = uuid.UUID('210c896b-de91-4e42-9910-a9a10ba219ef')
MAC_NAME = 'Shuffle Sync Wallpapers (macOS)'
IPHONE_NAME = 'Shuffle Sync Wallpapers (iOS)'
SUCCESS_DATE_KEY = 'last-successful-pacific-date'
ICON = {'WFWorkflowIconStartColor': 255, 'WFWorkflowIconGlyphNumber': 61460}


def variable(name):
    return {'WFSerializationType': 'WFTextTokenAttachment',
            'Value': {'Type': 'Variable', 'VariableName': name}}


def input_variable():
    return {'WFSerializationType': 'WFTextTokenAttachment',
            'Value': {'Type': 'ExtensionInput'}}


def tokens(*parts):
    text, attachments = '', {}
    for part in parts:
        if isinstance(part, dict) and part.get('WFSerializationType') == 'WFTextTokenAttachment':
            offset = len(text.encode('utf-16-le')) // 2
            attachments['{%d, 1}' % offset] = part['Value']
            text += '\ufffc'
        else:
            text += str(part)
    return {'WFSerializationType': 'WFTextTokenString',
            'Value': {'string': text, 'attachmentsByRange': attachments}}


class Shortcut:
    def __init__(self, name):
        self.name, self.actions = name, []
        self.accepts_input = False

    def uid(self, kind='action'):
        return str(uuid.uuid5(NAMESPACE, '%s/%s/%d' % (self.name, kind, len(self.actions)))).upper()

    def add(self, name, **parameters):
        identifier = name if name.startswith('is.workflow.actions.') else 'is.workflow.actions.' + name
        uid = parameters.setdefault('UUID', self.uid())
        self.actions.append({'WFWorkflowActionIdentifier': identifier,
                             'WFWorkflowActionParameters': parameters})
        return {'WFSerializationType': 'WFTextTokenAttachment',
                'Value': {'Type': 'ActionOutput', 'OutputUUID': uid, 'OutputName': 'Result'}}

    def text(self, *parts):
        return self.add('gettext', WFTextActionText=tokens(*parts))

    def set(self, name, value):
        self.add('setvariable', WFVariableName=name, WFInput=value)
        return variable(name)

    def number(self, value):
        return self.add('number', WFNumberActionNumber=tokens(value) if isinstance(value, dict) else value)

    def math(self, left, operation, right):
        def field(value):
            return tokens(value) if isinstance(value, dict) else value
        if operation == '%':
            return self.add('math', WFInput=field(left), WFMathOperation='…',
                            WFScientificMathOperation='Modulus', WFScientificMathOperand=field(right))
        return self.add('math', WFInput=field(left), WFMathOperation=operation,
                        WFMathOperand=field(right))

    def floor(self, value):
        return self.add('round', WFInput=tokens(value), WFRoundTo='Ones Place',
                        WFRoundMode='Always Round Down')

    def get(self, dictionary, key):
        return self.add('getvalueforkey', WFInput=dictionary,
                        WFDictionaryKey=tokens(key), WFGetDictionaryValueType='Value')

    def dictionary(self):
        return self.add('dictionary', WFItems={'WFSerializationType': 'WFDictionaryFieldValue',
                        'Value': {'WFDictionaryFieldValueItems': []}})

    def put(self, dictionary, key, value):
        return self.add('setvalueforkey', WFDictionary=dictionary,
                        WFDictionaryKey=tokens(key), WFDictionaryValue=tokens(value))

    def if_(self, value, condition=100, equals=None, numeric=False):
        group = self.uid('if')
        parameters = {'GroupingIdentifier': group, 'WFControlFlowMode': 0,
                      'WFInput': {'Type': 'Variable', 'Variable': value}, 'WFCondition': condition}
        if equals is not None:
            parameters['WFNumberValue' if numeric else 'WFConditionalActionString'] = (
                tokens(equals) if isinstance(equals, dict) else equals)
        self.add('conditional', **parameters)
        return group

    def otherwise(self, group):
        self.add('conditional', GroupingIdentifier=group, WFControlFlowMode=1)

    def end_if(self, group):
        return self.add('conditional', GroupingIdentifier=group, WFControlFlowMode=2)

    def repeat(self, count=None, items=None):
        group = self.uid('repeat')
        if items is not None:
            self.add('repeat.each', GroupingIdentifier=group, WFControlFlowMode=0, WFInput=items)
            return ('repeat.each', group)
        self.add('repeat.count', GroupingIdentifier=group, WFControlFlowMode=0,
                 WFRepeatCount=tokens(count) if isinstance(count, dict) else count)
        return ('repeat.count', group)

    def end_repeat(self, group):
        return self.add(group[0], GroupingIdentifier=group[1], WFControlFlowMode=2)

    def stop(self, value):
        return self.add('output', WFOutput=tokens(value), WFNoOutputSurfaceBehavior='Do Nothing')

    def comment(self, text):
        self.add('comment', WFCommentActionText=text)

    def write(self, path):
        value = {'WFWorkflowName': self.name, 'WFWorkflowActions': self.actions,
                 'WFWorkflowClientVersion': '4018.0.4', 'WFWorkflowMinimumClientVersion': 900,
                 'WFWorkflowMinimumClientVersionString': '900',
                 'WFWorkflowIcon': dict(ICON),
                 'WFWorkflowInputContentItemClasses': (
                     ['WFStringContentItem', 'WFDictionaryContentItem'] if self.accepts_input else []),
                 'WFWorkflowOutputContentItemClasses': [], 'WFWorkflowTypes': [],
                 'WFWorkflowImportQuestions': [], 'WFWorkflowHasOutputFallback': False,
                 'WFWorkflowHasShortcutInputVariables': self.accepts_input}
        Path(path).write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY, sort_keys=True))
        return value


def emit_rotation(s, n, day, diagnostics=True):
    zero = s.if_(n, 4, 0, numeric=True)
    s.stop(s.text('{"status":"empty","count":0}'))
    s.end_if(zero)
    cycle = s.set('cycle-number', s.floor(s.math(day, '÷', n)))
    position = s.set('cycle-position', s.math(day, '%', n))
    s.set('selected-index', s.number(0))
    two = s.if_(n, 4, 2, numeric=True)
    s.set('selected-index', position)
    s.otherwise(two)
    one = s.if_(n, 4, 1, numeric=True)
    s.set('selected-index', s.number(0))
    s.otherwise(one)

    # The final raw item of the previous Fisher-Yates permutation is fixed by its first swap.
    # Only six generator steps are needed to obtain it, without building that permutation.
    previous_seed = s.math(s.math(cycle, '+', 104728), '%', 2147483646)
    state = s.set('rng-state', s.math(previous_seed, '+', 1))
    warm = s.repeat(6)
    s.set('rng-state', s.math(s.math(state, '×', 48271), '%', 2147483647))
    s.end_repeat(warm)
    previous_last = s.set('previous-last', s.math(state, '%', n))

    state = s.set('rng-state', s.math(s.math(s.math(cycle, '+', 104729), '%', 2147483646), '+', 1))
    warm = s.repeat(5)
    s.set('rng-state', s.math(s.math(state, '×', 48271), '%', 2147483647))
    s.end_repeat(warm)

    permutation = s.set('permutation', s.dictionary())
    initialize = s.repeat(n)
    index = s.math(variable('Repeat Index'), '-', 1)
    s.set('permutation', s.put(permutation, index, index))
    s.end_repeat(initialize)

    swaps = s.repeat(s.math(n, '-', 1))
    i = s.set('swap-i', s.math(n, '-', variable('Repeat Index')))
    s.set('rng-state', s.math(s.math(state, '×', 48271), '%', 2147483647))
    j = s.set('swap-j', s.math(state, '%', s.math(i, '+', 1)))
    value_i = s.set('value-i', s.get(permutation, i))
    value_j = s.set('value-j', s.get(permutation, j))
    s.set('permutation', s.put(permutation, i, value_j))
    s.set('permutation', s.put(permutation, j, value_i))
    s.end_repeat(swaps)

    first = s.set('first-item', s.number(s.get(permutation, 0)))
    boundary = s.if_(first, 4, previous_last, numeric=True)
    second = s.set('second-item', s.get(permutation, 1))
    s.set('permutation', s.put(permutation, 0, second))
    s.set('permutation', s.put(permutation, 1, first))
    s.end_if(boundary)
    s.set('selected-index', s.number(s.get(permutation, position)))
    s.end_if(one)
    s.end_if(two)
    if not diagnostics:
        return variable('selected-index')
    result = s.text('{"status":"selected","count":', n, ',"day":', day,
                    ',"cycle":', cycle, ',"position":', position,
                    ',"index":', variable('selected-index'), '}')
    return result


def arguments(s):
    result = s.set('arguments', s.dictionary())
    supplied = s.if_(input_variable())
    s.set('arguments', s.add('detect.dictionary', WFInput=input_variable()))
    s.end_if(supplied)
    return result


def image_folder(s, args):
    folder = s.set('image-folder', s.text('Images'))
    if args is None:
        return folder
    override = s.get(args, 'folder')
    supplied = s.if_(override)
    allowed = s.add('text.match', text=tokens(override),
                    WFMatchTextPattern=r'(?-i)^(Images|QA-[A-Za-z0-9_-]+|\.local/fixtures/[A-Za-z0-9_-]+)$',
                    WFMatchTextCaseSensitive=True)
    valid = s.if_(allowed)
    s.set('image-folder', override)
    s.otherwise(valid)
    s.stop(s.text('{"status":"invalid_folder"}'))
    s.end_if(valid)
    s.end_if(supplied)
    return folder


def pacific_day(s, args):
    if args is None:
        now = s.add('date', WFDateActionMode='Current Date')
        converted = s.add('converttimezone', Date=tokens(now), DestinationTimeZone={
            'timeZone': 'America/Los_Angeles', 'alCityIdentifier': 152,
            'localizedCityName': 'Los Angeles, U.S.A.'})
        label = s.set('pacific-date', s.add('format.date', WFDate=tokens(converted),
            WFDateFormatStyle='Custom', WFDateFormat='yyyy-MM-dd', WFTimeFormatStyle='None',
            WFLocale='en_US_POSIX'))
        seconds = s.add('gettimebetweendates', WFTimeUntilFromDate='1970-01-01T00:00:00Z',
                        WFInput=tokens(label, 'T00:00:00Z'), WFTimeUntilUnit='Seconds')
        return label, s.set('day-number', s.floor(s.math(seconds, '÷', 86400)))
    as_of = s.get(args, 'as_of')
    supplied = s.if_(as_of)
    calendar_label = s.add('text.match', text=tokens(as_of),
                          WFMatchTextPattern=r'^\d{4}-\d{2}-\d{2}$')
    plain_date = s.if_(calendar_label)
    label = s.set('pacific-date', as_of)
    s.otherwise(plain_date)
    moment = s.add('date', WFDateActionMode='Specified Date', WFDateActionDate=tokens(as_of))
    converted = s.add('converttimezone', Date=tokens(moment), DestinationTimeZone={
        'timeZone': 'America/Los_Angeles', 'alCityIdentifier': 152,
        'localizedCityName': 'Los Angeles, U.S.A.'})
    s.set('pacific-date', s.add('format.date', WFDate=tokens(converted),
          WFDateFormatStyle='Custom', WFDateFormat='yyyy-MM-dd', WFTimeFormatStyle='None',
          WFLocale='en_US_POSIX'))
    s.end_if(plain_date)
    s.otherwise(supplied)
    now = s.add('date', WFDateActionMode='Current Date')
    converted = s.add('converttimezone', Date=tokens(now), DestinationTimeZone={
        'timeZone': 'America/Los_Angeles', 'alCityIdentifier': 152,
        'localizedCityName': 'Los Angeles, U.S.A.'})
    s.set('pacific-date', s.add('format.date', WFDate=tokens(converted),
          WFDateFormatStyle='Custom', WFDateFormat='yyyy-MM-dd', WFTimeFormatStyle='None',
          WFLocale='en_US_POSIX'))
    s.end_if(supplied)
    seconds = s.add('gettimebetweendates', WFTimeUntilFromDate='1970-01-01T00:00:00Z',
                    WFInput=tokens(label, 'T00:00:00Z'), WFTimeUntilUnit='Seconds')
    return label, s.set('day-number', s.floor(s.math(seconds, '÷', 86400)))


def daily_success_guard(s):
    """Stop repeat production runs before accessing the image file provider."""
    label, day = pacific_day(s, None)
    previous = s.add('getstoredcontent', WFStoredContentKey=SUCCESS_DATE_KEY,
                     WFStoredContentGlobalValue=False)
    # Coerce to text so an empty initial value and ISO dates compare as strings.
    previous = s.text(previous)
    completed = s.if_(previous, 4, label)
    s.stop(s.text('{"status":"already_completed"}'))
    s.end_if(completed)
    return label, day


def record_daily_success(s, label):
    s.add('setstoredcontent', WFInput=tokens(label), WFStoredContentKey=SUCCESS_DATE_KEY,
          WFStoredContentGlobalValue=False)


def emit_catalog(s, binding, args, platform='mac', date=None):
    folder = image_folder(s, args)
    label, day = date if date is not None else pacific_day(s, args)
    directory = s.add('documentpicker.open', WFFile=binding, WFGetFilePath=tokens(folder),
                      WFFileErrorIfNotFound=False, WFGetFolderContents=False)
    available = s.if_(directory)
    s.otherwise(available)
    s.stop(s.text('{"status":"unavailable","date":"', label, '"}'))
    s.end_if(available)
    files = s.add('file.getfoldercontents', WFFolder=directory, Recursive=False)
    present = s.if_(files)
    s.otherwise(present)
    s.stop(s.text('{"status":"empty","count":0,"date":"', label, '","stage":"folder"}'))
    s.end_if(present)
    scanned = s.set('scanned-count', s.add('count', Input=files, WFCountType='Items')) if args is not None else None
    # Resolve the localized image type once from a tiny embedded PNG. Comparing
    # native types avoids a format allowlist or an English-only "Image" literal.
    reference = s.add('base64encode', WFEncodeMode='Decode', WFInput=s.text(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII='))
    image_type = s.set('image-type', s.add('getitemtype', WFInput=s.add('detect.images', WFInput=reference)))
    names = s.set('filenames-by-key', s.dictionary())
    sortable = s.set('sortable-images', s.add('list', WFItems=[]))
    each = s.repeat(items=files)
    kind = s.add('getitemtype', WFInput=variable('Repeat Item'))
    is_image = s.if_(kind, 4, image_type)
    if platform == 'iphone':
        # iOS returned extensionless names for File Path in the physical-device
        # run. Rebuild the full name before hashing, not only at file lookup.
        basename = s.add('properties.files', WFInput=variable('Repeat Item'),
                         WFContentItemPropertyName='Name')
        extension = s.set('candidate-extension', s.add('properties.files',
                         WFInput=variable('Repeat Item'), WFContentItemPropertyName='File Extension'))
        filename = s.set('candidate-name', basename)
        has_extension = s.if_(extension)
        s.set('candidate-name', s.text(filename, '.', extension))
        s.end_if(has_extension)
    else:
        path = s.add('properties.files', WFInput=variable('Repeat Item'), WFContentItemPropertyName='File Path')
        filename = s.set('candidate-name', s.add('text.replace', WFInput=tokens(path),
            WFReplaceTextFind=r'^[\s\S]*/', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True,
            WFReplaceTextCaseSensitive=True))
    digest = s.add('hash', WFInput=s.text(filename), WFHashType='SHA256')
    # Prefix every hex digit to prevent natural file sorting from interpreting
    # digit runs as numbers. These ASCII-only virtual names sort as digest bytes.
    key = s.set('candidate-key', s.add('text.replace', WFInput=tokens(digest),
        WFReplaceTextFind=r'([0-9a-f])', WFReplaceTextReplace='x$1',
        WFReplaceTextRegularExpression=True, WFReplaceTextCaseSensitive=True))
    already = s.if_(s.get(names, key))
    s.stop(s.text('{"status":"catalog_key_collision","date":"', label, '"}'))
    s.end_if(already)
    s.set('filenames-by-key', s.put(names, key, filename))
    # Set Name receives fresh text, never an original catalog file.
    virtual = s.add('setitemname', WFInput=s.text(key), WFName=tokens(key), WFDontIncludeFileExtension=True)
    s.add('appendvariable', WFVariableName='sortable-images', WFInput=virtual)
    s.otherwise(is_image)
    s.add('nothing')
    s.end_if(is_image)
    s.end_repeat(each)
    count = s.set('image-count', s.add('count', Input=sortable, WFCountType='Items'))
    empty = s.if_(count, 4, 0, numeric=True)
    if args is not None:
        s.stop(s.text('{"status":"empty","count":0,"date":"', label,
                      '","stage":"filter","scanned":', scanned, '}'))
    else:
        s.stop(s.text('{"status":"empty"}'))
    s.end_if(empty)
    ordered = s.add('filter.files', WFContentItemInputParameter=sortable, WFContentItemSortProperty='Name',
                    WFContentItemSortOrder='A to Z', WFContentItemLimitEnabled=False)
    return names, ordered, label, folder


def emit_iphone_application(s, image, selected, poster=None, success_date=None):
    # Diagnostics return before this point. A phone-only final step also protects
    # the Mac if this synced shortcut is run normally on the computer.
    model = s.add('getdevicedetails', WFDeviceDetail='Device Model')
    iphone = s.add('text.match', text=tokens(model),
                   WFMatchTextPattern=r'(?i)^iPhone(?:\b|$)', WFMatchTextCaseSensitive=False)
    supported = s.if_(iphone)
    s.otherwise(supported)
    s.stop(s.text(s.put(selected, 'status', 'unsupported_device')) if selected else
           s.text('{"status":"unsupported_device"}'))
    s.end_if(supported)
    s.comment('Setup: Select your existing Photos wallpaper pair in Set Wallpaper Photo below. '
              'Then set the following Number to 1 and leave it at 1 for automatic updates.')
    # This is a build-time setting, never a shortcut-input option. An unbound
    # export must not fall through to Apple's Default Wallpaper behavior.
    ready = s.number(1 if poster else 0)
    unconfigured = s.if_(ready, 4, 0, numeric=True)
    s.stop(s.text(s.put(selected, 'status', 'setup_required')) if selected else
           s.text('{"status":"setup_required"}'))
    s.end_if(unconfigured)
    parameters = dict(WFInput=image, WFWallpaperLocation=['Lock Screen', 'Home Screen'],
                      WFWallpaperShowPreview=False, WFWallpaperPerspectiveZoom=False,
                      WFWallpaperSmartCrop=False, WFWallpaperLegibilityBlur=False)
    if poster:
        parameters['WFSelectedPoster'] = poster
    s.add('wallpaper.set', **parameters)
    if success_date is not None:
        record_daily_success(s, success_date)
    s.stop(s.text(s.put(selected, 'status', 'applied')) if selected else s.text('{"status":"applied"}'))


def build_sync(binding, platform='mac', iphone_poster=None, diagnostics=False,
               cache_directory=DEFAULT_CACHE_DIRECTORY):
    if platform not in {'mac', 'iphone'}:
        raise ValueError('Unsupported platform: %s' % platform)
    s = Shortcut(MAC_NAME if platform == 'mac' else IPHONE_NAME)
    s.accepts_input = diagnostics
    args = arguments(s) if diagnostics else None
    date = None if diagnostics else daily_success_guard(s)
    if diagnostics:
        # Diagnostic actions are excluded from the installed production exports.
        mode = s.text(s.get(args, 'mode'))
        diagnostic = s.if_(mode, 4, 'index')
        s.set('image-count', s.number(s.get(args, 'count')))
        s.set('day-number', s.number(s.get(args, 'day')))
        s.otherwise(diagnostic)
    names, ordered, label, folder = emit_catalog(s, binding, args, platform, date)
    if diagnostics:
        s.end_if(diagnostic)
    # Both normal execution and index diagnostics pass through this single copy
    # of the rotation algorithm. There are no Run Shortcut actions or dependencies.
    rotation = emit_rotation(s, variable('image-count'), variable('day-number'), diagnostics)
    if diagnostics:
        diagnostic = s.if_(mode, 4, 'index')
        s.stop(rotation)
        s.end_if(diagnostic)
        result = s.add('detect.dictionary', WFInput=rotation)
        index = s.set('selected-index', s.number(s.get(result, 'index')))
    else:
        index = rotation
    chosen = s.add('getitemfromlist', WFInput=ordered, WFItemSpecifier='Item At Index',
                   WFItemIndex=tokens(s.math(index, '+', 1)))
    chosen_key = s.add('properties.files', WFInput=chosen, WFContentItemPropertyName='Name')
    filename = s.get(names, chosen_key)
    selected = None
    if diagnostics:
        result = s.put(result, 'filename', filename)
        result = s.put(result, 'date', label)
        result = s.put(result, 'folder', folder)
        selected = s.set('selection', result)
        selection_only = s.if_(mode, 4, 'select')
        s.stop(s.text(selected))
        s.end_if(selection_only)
        filename = s.get(selected, 'filename')
    has_selection = s.if_(filename)
    s.otherwise(has_selection)
    s.stop(s.text(selected) if selected else s.text('{"status":"unavailable"}'))
    s.end_if(has_selection)
    if diagnostics:
        folder = s.get(selected, 'folder')
    file = s.add('documentpicker.open', WFFile=binding, WFGetFilePath=tokens(folder, '/', filename),
                 WFFileErrorIfNotFound=False)
    present = s.if_(file)
    s.otherwise(present)
    s.stop(s.text('{"status":"unavailable"}'))
    s.end_if(present)
    images = s.add('detect.images', WFInput=file)
    decoded = s.if_(images)
    s.otherwise(decoded)
    s.stop(s.text('{"status":"invalid_image"}'))
    s.end_if(decoded)
    # Get Images can return a lazy wrapper for invalid bytes. Resolve image dimensions
    # and materialize a PNG before reporting validation or reaching the setter.
    width = s.add('properties.images', WFInput=images, WFContentItemPropertyName='Width')
    has_width = s.if_(width)
    s.otherwise(has_width)
    s.stop(s.text('{"status":"invalid_image"}'))
    s.end_if(has_width)
    zero_width = s.if_(s.number(width), 4, 0, numeric=True)
    s.stop(s.text('{"status":"invalid_image"}'))
    s.end_if(zero_width)
    images = s.add('image.convert', WFInput=images, WFImageFormat='PNG', WFImagePreserveMetadata=True)
    if diagnostics:
        dry_run = s.if_(s.get(args, 'dry_run'))
        s.stop(s.text(s.put(selected, 'status', 'validated')))
        s.end_if(dry_run)
    image = s.add('getitemfromlist', WFInput=images, WFItemSpecifier='First Item')
    if platform == 'iphone':
        emit_iphone_application(s, image, selected, iphone_poster,
                                success_date=None if diagnostics else label)
    else:
        cache_source = Path(__file__).with_name('cache_image.py').read_text()
        script = ("/usr/bin/python3 - --cache-directory " + shlex.quote(cache_directory) +
                  " \"$@\" <<'WALLPAPER_PYTHON'\n" + cache_source + "\nWALLPAPER_PYTHON\n")
        s.add('runshellscript', Script=script, Input=image,
              InputMode='as arguments', UUID='3ACB2822-4965-44B2-A4E2-CC332C38956B')
        if not diagnostics:
            record_daily_success(s, label)
        s.stop(s.text(s.put(selected, 'status', 'prepared')) if selected else s.text('{"status":"prepared"}'))
    return s


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--folder-binding', type=Path, required=True)
    parser.add_argument('--platform', choices=['mac', 'iphone'], default='mac')
    parser.add_argument('--diagnostics', action='store_true',
                        help='Include test inputs and detailed results in a separate development build')
    parser.add_argument('--iphone-poster', type=Path,
                        help='Previously verified native WFSelectedPoster plist for this iPhone')
    parser.add_argument('--cache-directory', default=DEFAULT_CACHE_DIRECTORY,
                        help='Mac cache directory relative to the home folder')
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    binding = plistlib.loads(options.folder_binding.read_bytes())
    if options.iphone_poster and options.platform != 'iphone':
        parser.error('--iphone-poster requires --platform iphone')
    poster = plistlib.loads(options.iphone_poster.read_bytes()) if options.iphone_poster else None
    shortcut = build_sync(binding, options.platform, poster, diagnostics=options.diagnostics,
                          cache_directory=options.cache_directory)
    if options.diagnostics:
        shortcut.name += ' Development'
    shortcut.write(options.output / (shortcut.name + '.unsigned.shortcut'))
