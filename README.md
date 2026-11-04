# Wallpaper Sync

Build native Mac and iPhone shortcuts that independently select the same daily wallpaper from a shared image folder. Selection uses the Gregorian date in `America/Los_Angeles` and the catalog's original filenames. It needs no server, account credentials, or stored rotation history.

## Requirements

- A Mac with Shortcuts and Python 3.9 or later
- `/usr/bin/python3` available for the Mac shortcut's inline cache writer
- An iCloud Drive project folder available on each participating device
- Images stored directly in the project's `Images` folder

The native action formats target macOS 27 and iOS 27. Earlier versions have not been validated. Generating an export does not import it, grant folder access, configure a wallpaper pair, or install automation triggers.

## Local Setup

Keep the checkout in an iCloud Drive folder accessible to each device. Its location and account name are never hardcoded in source. Create the ignored setup file:

```sh
python3 scripts/build_shortcuts.py --init
```

Edit `.local/setup.json`. The public `setup.example.json` contains the supported fields:

| Field | Purpose |
| --- | --- |
| `version` | Configuration schema version, currently `1` |
| `platforms` | Build `mac`, `iphone`, or both |
| `folder_binding` | Path to a captured native project-folder reference under `.local` |
| `iphone_poster` | Optional native wallpaper-pair plist under `.local`, or `null` |
| `output` | Generated export directory under `Shortcuts` or `.local` |
| `cache_directory` | Mac cache path relative to the home folder, under `Library/Application Support` |

Configuration paths are relative to the repository, regardless of the shell's working directory. The cache path is relative to the executing user's home folder. The default is `Library/Application Support/Wallpaper Sync/Current`. No name, email address, device serial number, or Apple account password is needed.

### Capture the Project Folder

Apple's native folder reference includes file-provider identifiers. Obtain a reference from the consumer's own Shortcuts selection instead of typing or copying identifiers from another account:

1. In Shortcuts on Mac, create a temporary shortcut named `Wallpaper Sync Setup`.
2. Add Get File from Folder. Select the project's root folder with its folder picker and set its relative path to `Images`.
3. Save the shortcut. It does not need to run.
4. Capture its selected folder:

```sh
python3 scripts/build_shortcuts.py --capture-folder 'Wallpaper Sync Setup'
python3 scripts/build_shortcuts.py --check
```

Capture reads the native Shortcuts database in read-only mode and writes the selected reference to the configured ignored plist. It requires one unambiguous shortcut name and one distinct folder reference. If the database is inaccessible, the command stops without changing native data. Keep the setup shortcut until exports are built and folder access is verified through normal installation.

Existing local configuration and binding files are preserved. To deliberately refresh a captured reference, repeat capture with `--replace`. `--init` never overwrites an existing setup file.

## Build the Shortcuts

```sh
python3 scripts/build_shortcuts.py
```

The command validates the setup and inputs before generating the configured exports. Production filenames are:

- `Shuffle Sync Wallpapers (macOS).unsigned.shortcut`
- `Shuffle Sync Wallpapers (iOS).unsigned.shortcut`

Sign local exports for import when needed:

```sh
python3 scripts/build_shortcuts.py --sign
```

Signing uses Apple's `shortcuts sign --mode anyone` and sends the generated exports to Apple for validation. Signed filenames omit `.unsigned`. The build command does not install or run them. [Apple documents signing modes and validation](https://support.apple.com/guide/shortcuts-mac/apd455c82f02/mac).

Generated exports contain the selected folder reference and may contain a configured wallpaper-pair reference. Keep personalized exports out of source control, including signed exports. They are not generic distribution templates.

After importing the configured shortcuts on Mac, optional installation discovery records their local identifiers without changing Shortcuts:

```sh
python3 scripts/build_shortcuts.py --record-installation
```

The result stays in `.local/install.json`. If the recorded installation changes, explicitly use `--replace` to update that record.

## Daily Completion

Each production shortcut saves one value in native Shortcuts storage: The Pacific date of its last successful run. If that date matches today, the shortcut returns `already_completed` before opening the image folder, scanning the catalog, decoding an image, or running the Mac cache writer. There is no separate status file, database, or failure history.

The iPhone shortcut saves the date after Set Wallpaper Photo returns. The Mac shortcut saves it after the cache writer returns successfully. Mac completion means the cache is prepared for native wallpaper rotation, not that every display has rendered the image. Failures and early exits leave the saved date unchanged, allowing a later trigger to try again. A different Pacific date permits a new run without a separate reset automation.

Storage is scoped to each shortcut with Global Value off. Development exports bypass the daily check and do not update the production success value. Changes to the catalog, cache, or wallpaper after a successful run are not checked again that day. Clear `last-successful-pacific-date` in the shortcut's storage view when a deliberate same-day refresh is needed.

## Mac Installation

Import the signed macOS export. Select the project folder again in its Get File from Folder actions if Shortcuts requests authorization. Allow Running Scripts in Shortcuts is required for the inline Python writer.

Run the shortcut to populate the configured cache. The default location is:

```text
~/Library/Application Support/Wallpaper Sync/Current
```

In System Settings → Wallpaper, add that folder as a photo source. Choose its Shuffle tile, select Every Minute, and enable Show on all Spaces. The writer maintains two identical files, `wallpaper-1.png` and `wallpaper-2.png`, because native folder rotation needs multiple entries for its Shuffle source.

The shortcut prepares the daily image in the background. Native Wallpaper rotation displays it afterward. The `prepared` result confirms cache publication, not immediate rendering on every display.

Add Time of Day automation triggers in Shortcuts for the desired check times. An hourly schedule uses 24 daily triggers at minute `00`. Enable running when locked and turn Notify off where available. Trigger times use the device's local clock, while image selection always uses the shared Pacific date. Device sleep and operating-system scheduling can delay execution.

See [iPhone installation](docs/iphone.md) for the phone-specific setup.

## Images and Selection

Copy images directly into `Images`, preserving their original names. Native image-type recognition excludes non-image files and subfolders. Filenames can contain spaces, punctuation, Unicode, and different extensions. Identical base names with different extensions are separate images.

The catalog order is the ascending SHA-256 digest of each full filename's UTF-8 bytes. Native sorting uses temporary digest labels with separated characters to avoid numeric collation differences. Original files are not renamed.

Let `N` be the image count and `d` the days since `1970 Jan 1` for the Pacific date. The cycle is `floor(d / N)`, and the position is `d mod N`. For at least three images, the selector creates a Fisher-Yates permutation from a deterministic multiplicative generator and prevents a repeat across cycle boundaries. Two images alternate by day, and one image remains selected.

An unchanged catalog shows every image once per cycle without consecutive repeats. Adding, removing, or renaming images can change the current selection. Devices need the same catalog, filenames, and date rule to agree. iCloud synchronization delays can temporarily produce different selections.

Empty, missing, or invalid image input preserves the current wallpaper. The Mac writer validates PNG structure and checksums, locks overlapping writers, stages complete files, and replaces fixed cache files atomically. Repeated identical input leaves cache files untouched. Cache confidentiality also depends on the host's home-directory permissions.

## Development and Verification

Run the portable automated checks without importing shortcuts or accessing native device data:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Development exports include restricted diagnostic inputs and detailed results:

```sh
python3 scripts/build_shortcuts.py --diagnostics
```

These exports go under `.local/development`. Import separate copies with the `Development` suffix to use the native integration tools. Production ignores shortcut input and excludes date, folder, and arithmetic overrides.

See [validation](docs/validation.md) for test scope and native integration prerequisites.

## Publication Privacy

Commit source, portable tests, general documentation, and `setup.example.json`. Keep `.local`, images, generated shortcuts, receipts, private keys, environment files, and QA fixtures ignored. Store installation observations and hardware-specific notes under `.local`.

Before publishing, review the staged diff and file list. Files previously committed remain in Git history even after deletion or the addition of ignore rules. Publish a reviewed source snapshot with fresh history if previous private development records should stay private. Git author metadata is separate from application setup. [GitHub documents commit email privacy](https://docs.github.com/en/account-and-profile/concepts/email-addresses).

After staging the intended source files, run the publication check against the exact staged bytes:

```sh
python3 scripts/check_publication.py
git diff --cached --check
```

The check rejects recognized private artifacts, absolute account paths, credential patterns, and nonexample email addresses. It supplements a review of the staged content and does not inspect old history or guarantee that every sensitive value is recognizable.
