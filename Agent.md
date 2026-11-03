# Agent.md — oldcook Operating Manual

## 1. Mission & Core Architecture
`oldcook` is a Linux-first, auto-updating overlay factory for backporting modern Flutter (3.47+) and native open-source iOS apps (primary target: `bggRGjQaUbCoE/PiliPlus`) to **iOS 12** without rolling back upstream commits or maintaining polluted forks.

- **Deployment Baseline (`12.2`)**: All A7/A8 iOS 12 devices (`iPhone 5s`, `iPhone 6`, `iPad Air 1`, `iPad mini 2/3`, `iPod touch 6`) run up to **iOS 12.5.7** (jailbreak baseline: **12.4**). Targeting `12.2` unlocks Apple's OS-bundled ABI-stable Swift 5 runtime (`/usr/lib/swift/libswift*.dylib`) and avoids Xcode 16's removal of pre-12.2 bundled Swift stdlib slices, while `12.0` remains available for pure C/ObjC targets.
- **Four-Layer Decoupled Reuse**:
  1. `engine-patches/patch_flutter_ios12.py`: Semantic, version-resilient Python patcher for `flutter/flutter` (`--mode tools-only` unlocks `flutter_tools` + `podhelper.rb`; `--mode full` also patches `engine/src/` C++/ObjC++/Swift embedder for `12.2` + `-Wl,-ld_classic` + `-fno-aligned-allocation`).
  2. `compat-packages/ios12_polyfill/` + `tools/patch_ios_sources.py`: Runtime Objective-C `+load` polyfill (`UIColor`, `UIImage`, `UIScene` selectors) plus post-`pub get` plugin vendor/patcher (`.oldcook_plugins/`), keeping global `~/.pub-cache` clean.
  3. `recipes/<name>/recipe.json` + `tools/apply_recipe.py`: Declarative per-app overlay (upstream URL, upstream pre-build hooks like `PiliPlus` `build.ps1`/`patch.ps1`, Podfile/pbxproj/Info.plist injection, weak framework & Swift overlay flags).
  4. `tools/audit_ipa.py` + `tools/check_upstream.py` + `.github/workflows/auto-sync.yml`: Scheduled upstream release tracker, cloud `macos-15` builder, and strict Linux/CI Mach-O gatekeeper verified against `sdks/iPhoneOS12.4.sdk` (`.tbd` symbol ground truth).

## 2. Verified `PiliPlus` (Flutter 3.47.9) Ground Truth
- **Media Core Already Compatible**: All 19 bundled `Mpv` / `FFmpeg` / `Dav1d` / `Ass` / `Placebo` frameworks from `My-Responsitories/media-kit` (`ref: native`) already ship with `LC_VERSION_MIN_IPHONEOS = 11.0`, `LC_DYLD_INFO_ONLY` (no chained fixups), and `0` missing iOS 12 symbols. Do NOT waste compute recompiling `ffmpeg`/`libmpv` unless upstream switches media libraries.
- **Engine Gap (`Flutter.framework`) & `App.framework` Relinking**:
  - `Flutter.framework` does NOT link `libswift_Concurrency.dylib` in `3.47.9`. Lowering `ios_deployment_target` to `"12.2"` with `-fno-aligned-allocation` plus guarding 10 call sites (`UISceneWillConnectNotification` in `FlutterEngine.mm`, `CAFrameRateRangeMake`, `kCACornerCurve*`, `eventAttribution`, `UIAccessibilitySpeechAttributeSpellOut`, `FlutterTextInputPlugin.mm` `UIMenu` helpers, `FlutterSceneDelegate`/`FlutterSceneLifeCycle`, and `AccessibilityFeatures.swift` `onOffSwitchLabels`/`videosAutoPlay`) eliminates `LC_DYLD_CHAINED_FIXUPS(0x80000034)` and converts remaining iOS 13+ symbols to safe weak imports.
  - `gen_snapshot` in Flutter 3.47.9 emits `App.framework/App` without `LC_DYLD_INFO_ONLY` and places `LC_SEGMENT_64 (__TEXT)` at load command 6, which iOS 12 `dyld2` rejects on `dlopen()`. `tools/relink_app_framework.py` extracts `__TEXT,__text` (`_kDartSnapshotText`), `__TEXT,__const` (`_kDartSnapshotData`), and a 16KB-aligned writable `.zerofill __DATA,__bss` (required by `dart::BSS::Initialize` at VMA `0x189c000`) and relinks it into a standard `LC_DYLD_INFO_ONLY` Mach-O dylib without `CS_LINKER_SIGNED (0x20000)`.
  - `compat-packages/ios12_polyfill/Sources/IOS12Polyfill.m` provides `+load` runtime shims verified on real iPhone 6s Plus (`iOS 12.4.1`) hardware: `MTLDevice` (`supportsFamily:` bridged to `supportsFeatureSet:`, `hasUnifiedMemory`), `OCIOS12WindowSceneProxy` & `OCIOS12StatusBarManagerProxy` (`-[UIWindow windowScene]`, `-[UIApplication connectedScenes]`), `UITraitCollection` (`accessibilityContrast`, `legibilityWeight`, `currentTraitCollection`), `NSFileHandle`, `PHPhotoLibrary`, `AVAudioSession`, `UIScrollView`, `UIButton`, `UIColor`, and `UIImage`.
- **App & Plugin Gap**:
  - `ios/Runner/PipPlugin.swift` is already `@available(iOS 15.0, *)` guarded; only `ios/Runner/SceneDelegate.swift` requires `@available(iOS 13.0, *)`.
  - SwiftPM must be disabled (`flutter config --no-enable-swift-package-manager`) so all plugins build via CocoaPods under `Podfile` `post_install` (`-Wl,-ld_classic`, `-Wl,-weak_framework,...`, `-Wl,-weak-lswift...`).
  - Native plugins requiring post-`pub get` source shims (`tools/patch_ios_sources.py`): generic `FlutterSceneLifeCycleDelegate` / `addSceneDelegate` guards, `file_picker_darwin` (iOS 12 `UIDocumentPickerViewController` + `UIImagePickerController` fallback), `cnativeapi` (`_LIBCPP_AVAILABILITY_DISABLE`), `share_plus`, `connectivity_plus`, and `flutter_inappwebview_ios`.

## 3. Standard Commands (Linux Host)
```bash
# Run full local verification suite (< 5s, zero network)
python3 tools/selftest.py

# Ensure iPhoneOS12.4.sdk (.tbd index) is installed locally
./tools/fetch_sdk.sh

# Audit any .ipa or .app bundle (exit code 0 = PASS, 2 = BLOCKED)
python3 tools/audit_ipa.py path/to/App.ipa --json dist/audit.json

# Check all recipes/*/recipe.json against live GitHub upstream releases
python3 tools/check_upstream.py

# Prepare a clean upstream workspace with iOS 12 recipe overlays
python3 tools/apply_recipe.py piliplus
```

## 4. Adding a New Open-Source App Recipe
1. Create `recipes/<app>/recipe.json` specifying `repo`, `ref` or `track` (`"release"` or `"branch"`), `min_ios` (`"12.2"` for Swift/Flutter, `"12.0"` for ObjC/C), and optional `pre_build_commands` / `extra_flutter_args`.
2. Run `python3 tools/apply_recipe.py <app>` and trigger `.github/workflows/reusable-flutter-ios12.yml`.
3. Inspect `dist/<app>-audit.json` from `tools/audit_ipa.py`. If a new native plugin introduces unguarded iOS 13+ symbols, add a targeted rule in `tools/patch_ios_sources.py` or place an override package in `compat-packages/<plugin_name>/`.

## 5. Token & Turn Economy Rules for Agents
- **Never touch host SDKs/caches**: Never edit `/home/luo/.local/share/flutter` or `~/.pub-cache` in place; always vendor plugin overrides into `work/<recipe>/.oldcook_plugins/` and test engine patches against temp copies.
- **Batch & filter**: Issue independent `read_file` / shell checks in parallel; cap command output (`head`, `grep`) to < 80 lines; run `python3 tools/selftest.py` in a single turn to validate changes.
- **Semantic transforms over line patches**: Prefer structural regex/AST rules in `patch_flutter_ios12.py`, `apply_recipe.py`, and `patch_ios_sources.py` over line-numbered `.patch` files so upstream updates never break unattended CI.
