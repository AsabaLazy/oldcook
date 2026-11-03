# oldcook: Auto-Updating Linux-First iOS 12 Backport Factory

Reusable overlay factory for backporting modern Flutter (3.47+) and native open-source iOS apps (such as `bggRGjQaUbCoE/PiliPlus`) to **iOS 12.2 ~ 12.5.7** without rolling back upstream commits.

See [Agent.md](file:///home/luo/Projects/oldcook/Agent.md) for detailed architecture, Mach-O audit findings, and maintenance rules.

## Core Components

- `engine-patches/patch_flutter_ios12.py`: Idempotent semantic patcher unlocking `flutter_tools` (`IOSDeploymentTargetMigration`, `podhelper.rb`, `native_assets.dart`) and patching `Flutter.framework` (`darwin_sdk.gni`, `-fno-aligned-allocation`, `-Wl,-ld_classic`, `@available` guards) for iOS 12.2.
- `compat-packages/ios12_polyfill/`: Automatic Objective-C `+load` runtime shim backfilling common iOS 13+ `UIColor`, `UIImage`, and `UIScene` selectors on iOS 12.
- `tools/apply_recipe.py` & `tools/patch_ios_sources.py`: Clones upstream cleanly into `work/<recipe>`, applies `Podfile` / `project.pbxproj` / `Info.plist` / `SceneDelegate.swift` hooks, and vendors/patches native plugins into `.oldcook_plugins/` without touching `~/.pub-cache`.
- `tools/audit_ipa.py`: Offline Linux Mach-O / `.ipa` gatekeeper checking `LC_BUILD_VERSION`, `LC_DYLD_CHAINED_FIXUPS`, dylibs, and symbols against `sdks/iPhoneOS12.4.sdk` (`.tbd`).
- `tools/check_upstream.py` & `.github/workflows/auto-sync.yml`: Daily upstream release watcher that auto-builds new engine releases when Flutter bumps, builds updated recipes on `macos-15`, gates releases with `audit_ipa.py`, and opens diagnostic Issues if blocked.
- `native-libs/ios12-toolchain.cmake` & `tools/sign_and_install.sh`: Linux C/C++ cross-compilation toolchain (`clang` + `cctools-port`) and local IPA signing/USB installation (`zsign` / `ldid` + `ideviceinstaller`).

## Quick Start (Linux)

```bash
# 1. Fetch iPhoneOS12.4.sdk (~9 MB) and run the offline self-test suite
./tools/fetch_sdk.sh
python3 tools/selftest.py

# 2. Check upstream GitHub releases across all recipes/*/recipe.json
python3 tools/check_upstream.py

# 3. Prepare PiliPlus workspace with iOS 12 overlays locally
python3 tools/apply_recipe.py piliplus

# 4. Audit any .ipa or .app bundle offline on Linux
python3 tools/audit_ipa.py path/to/App.ipa --json dist/audit.json
```
