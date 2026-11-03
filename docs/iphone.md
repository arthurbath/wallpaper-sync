# iPhone Installation

Build the iPhone export on a Mac using the local setup workflow in the [README](../README.md). Python constructs the shortcut and does not run on iPhone. The generated phone shortcut uses native actions and contains no shell script or helper shortcut.

## Import and Authorize

1. Add images to the shared project's `Images` directory and make the folder available offline on iPhone where possible.
2. Transfer the signed `Shuffle Sync Wallpapers (iOS).shortcut` export through Files or another chosen transfer method.
3. Import the shortcut. Select the project root in both Get File from Folder actions if their folder reference needs authorization. Preserve their relative paths.
4. In Set Wallpaper Photo, select an existing Photos wallpaper pair. Keep both Lock Screen and Home Screen selected, with Show Preview off.
5. After the setup Comment, change the standalone Number from `0` to `1`. Leave the `If Number is 0` comparison unchanged.

Fresh exports have no phone-specific wallpaper-pair reference unless an optional native plist was explicitly configured in local setup. Their setup Number stays `0`, causing `setup_required` until the existing pair is selected. Returning that Number to `0` disables application without removing the image catalog.

Apple may require local device permission even when a folder reference was captured on Mac. A typed filesystem path does not replace that authorization. Shortcuts iCloud Sync is independent of iCloud Drive file synchronization. Choose a distribution and sync approach appropriate to the installation rather than assuming the two settings are equivalent.

## Scheduling

Add Time of Day automation triggers for the desired schedule. For hourly checks, add 24 daily entries at minute `00`. Turn Notify off where offered and allow running when locked. A Charger → Is Connected trigger can add another refresh opportunity.

Each invocation computes the current Pacific selection. Missed days do not require replaying earlier selections. Powered-off devices, unavailable iCloud files, and system scheduling restrictions can delay a refresh.

The build process generates actions. It does not install native triggers, grant permissions, or configure the phone's wallpaper pair. [Apple documents native automation triggers and locked execution](https://support.apple.com/guide/shortcuts/apdfbdbd7123/ios).

## Behavior and Limits

The phone and Mac selectors share the same deterministic catalog ordering and rotation. iPhone reconstructs each full filename from its Name and File Extension before hashing. Original extension case and repeated extensions are retained.

The selected image must decode, have nonzero width, and convert to PNG before application. Empty, missing, or corrupt input stops before the wallpaper setter. A normal Mac invocation of the phone shortcut returns `unsupported_device` without applying it.

A generated file and a passing Mac build do not establish physical iPhone runtime behavior. Framing, locked operation, native scheduling, and wallpaper-pair behavior depend on iOS and the installed device state. Keep any device observations and native references in ignored local records.

## File Access Timeouts

If Shortcuts marks the first Get File from Folder action with `Shortcut Timed Out`, execution stopped while resolving the image directory, before catalog selection or wallpaper application. A successful manual run establishes that the folder and images were accessible at that time. It does not establish that iCloud Drive can resolve the folder during unattended execution.

Inspect Allow Running When Locked in the shortcut's Privacy settings and the folder's download state in Files. Use Keep Downloaded for the project folder or its image catalog. Files may show Show Downloaded Folder when an ancestor already supplies that setting. Download retention reduces dependence on network transfers, but the shortcut still accesses the iCloud file provider. [Apple documents keeping files downloaded](https://support.apple.com/guide/iphone/iphe9aff429a/ios).

For an imported shortcut, reselect the same project root through the iPhone folder picker in both Get File from Folder actions. Preserve the relative paths, existing wallpaper pair, and setup Number. This refreshes the device's folder references, but does not prove that a background timeout is resolved.

Separate scheduled attempts can produce separate failure notifications, including notifications surfaced when Shortcuts is opened. A notification burst alone does not establish duplicate triggers, automatic retries, or their execution times. Inspect the actual automation list before changing the schedule. Turning Notify off does not turn a failed run into a successful wallpaper update.

Validate a repaired shortcut with an unattended scheduled invocation as well as a foreground run. Record the observed conditions and result. A test after opening Files can have a warm file-provider session and does not reproduce an overnight cold session. If background file-access failures persist, a separate catalog under On My iPhone can remove iCloud from the application path, but it requires an explicit refresh process that preserves the shared catalog and original filenames. Treat that as a separate workflow change.
