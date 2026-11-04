# Validation

## Portable Checks

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The portable suite exercises rotation cycles, cross-cycle repeat prevention, filename ordering, time-zone boundaries, PNG validation, atomic cache replacement, idempotence, invalid-input retention, and symlink refusal. Setup tests cover private configuration, capture from a synthetic native database, generated action parity, and relocation to another checkout. Daily-completion checks inspect both production action graphs to verify that the repeat exit precedes file access, only the successful platform action can record the date, storage is scoped to each shortcut, and development exports do not read or write the success value. These checks do not execute Apple's storage actions.

Portable tests use synthetic image data and native-reference fixtures. They do not read personal Shortcuts data, import exports, run installed shortcuts, contact Apple, or change wallpaper settings.

## Local Build Checks

```sh
python3 scripts/build_shortcuts.py --check
python3 scripts/build_shortcuts.py
python3 scripts/build_shortcuts.py --diagnostics
```

Setup validation checks configuration shape, supported platforms, private input paths, output confinement, and native plist structure. Generation uses native actions from `src/native_builder.py`. The macOS export embeds `src/cache_image.py` and the configured cache location. The iPhone export uses the native wallpaper setter and its device/setup guards.

Folder capture and installation discovery use parameterized queries against the native Shortcuts database in read-only mode. Captured references and discovered identifiers remain under `.local`. These helpers do not write Apple's database.

## Optional Native Integration

Native integration tools require imported exports, appropriate folder permissions, a populated catalog, and a configured Mac wallpaper cache. Development tests require separately imported diagnostic exports. Production checks require the configured production shortcuts and a complete hourly Mac schedule.

```sh
python3 tests/native_core_test.py
python3 tests/native_selection_test.py
python3 tests/native_filename_test.py --receipt .local/validation/filenames.json
python3 tests/mac_guard_test.py
python3 tests/iphone_draft_test.py --receipt .local/validation/iphone.json
python3 tests/production_shortcuts_test.py --receipt .local/validation/production.json
python3 tests/native_schedule_test.py
```

Create `.local/validation` before requesting persistent receipts. Native tools invoke installed shortcuts and can exercise normal wallpaper preparation. Catalog tests use temporary `QA-` directories under the project and guard their cleanup. They compare the settled wallpaper configuration and cache where appropriate. The iPhone diagnostic test runs on Mac and verifies the device guard rather than claiming physical phone application.

Schedule inspection expects 24 enabled daily Mac triggers, one per hour at minute `00`, with locked execution allowed. On the targeted macOS action format, the verified native Notify-off representation is `1`. This value should be rechecked when adding support for a different operating-system version.

Store device-specific receipts, hardware observations, screenshots, installed identifiers, and recovery exports under ignored local storage. Public validation documentation describes the checks and their limits without embedding a person's environment or activity history.

## Evidence Boundaries

Source inspection, export generation, signing, import, schedule configuration, and observed device execution are distinct checks. Report only the layers actually exercised for a change. Build success does not establish sleep/wake catch-up, all-display rendering, physical iPhone behavior, or an operating system's permission decisions.
