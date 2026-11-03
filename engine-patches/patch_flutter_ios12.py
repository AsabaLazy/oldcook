#!/usr/bin/env python3
"""Idempotent semantic patcher lowering Flutter 3.47+ Tools & iOS Engine to iOS 12.2.

Modes:
  --mode tools-only : Unlocks packages/flutter_tools (IOSDeploymentTargetMigration + podhelper.rb)
                      so `flutter build ios` permits IPHONEOS_DEPLOYMENT_TARGET = 12.2.
  --mode full       : Applies tools-only PLUS patches engine/src/ GN configs, compiler/linker flags
                      (-fno-aligned-allocation, -Wl,-ld_classic, -Wno-unguarded-availability-new),
                      and @available(iOS 13+/14+/15+/16+) runtime guards in the iOS embedder.
"""

import argparse
import re
import sys
from pathlib import Path


def edit_if_present(path: Path, fn) -> bool:
    if not path.exists():
        return False
    orig = path.read_text(encoding="utf-8")
    updated = fn(orig)
    if updated != orig:
        path.write_text(updated, encoding="utf-8")
        print(f"[patched] {path}")
        return True
    return False


def patch_flutter_tools(flutter_root: Path, target_ios: str) -> int:
    changed = 0
    major = target_ios.split(".")[0]

    # 1. Disable IOSDeploymentTargetMigration forcing 12.x/13.x/14.x -> 15.0
    mig = (
        flutter_root
        / "packages/flutter_tools/lib/src/ios/migrations/ios_deployment_target_migration.dart"
    )

    def _fix_mig(text: str) -> str:
        if "// OLDCOOK_IOS12_UNLOCKED" in text:
            return text
        text = text.replace(
            "Future<void> migrate() async {",
            "Future<void> migrate() async {\n    // OLDCOOK_IOS12_UNLOCKED\n    return;",
            1,
        )
        return text

    changed += int(edit_if_present(mig, _fix_mig))

    # 2. Lower Flutter.podspec floor and inherit_deployment_target threshold in podhelper.rb
    podhelper = flutter_root / "packages/flutter_tools/bin/podhelper.rb"

    def _fix_podhelper(text: str) -> str:
        text = re.sub(
            r"target\.deployment_target\[/\\d\+/\]\.to_i\s*<\s*15",
            lambda _: f"target.deployment_target[/\\d+/].to_i < {major}",
            text,
        )
        text = re.sub(
            r"s\.ios\.deployment_target\s*=\s*['\"][0-9.]+['\"]",
            lambda _: f"s.ios.deployment_target = '{target_ios}'",
            text,
        )
        return text

    changed += int(edit_if_present(podhelper, _fix_podhelper))

    # 3. Lower hardcoded targetIOSVersion = 15 in Dart Native Assets (fixes objective_c.framework etc.)
    native_assets_ios = (
        flutter_root
        / "packages/flutter_tools/lib/src/isolated/native_assets/ios/native_assets.dart"
    )
    changed += int(
        edit_if_present(
            native_assets_ios,
            lambda t: re.sub(
                r"const\s+targetIOSVersion\s*=\s*\d+\s*;",
                f"const targetIOSVersion = {major};",
                t,
            ),
        )
    )

    # Invalidate compiled flutter_tools snapshot so next `flutter` command rebuilds it cleanly
    if changed:
        for snap in ("flutter_tools.snapshot", "flutter_tools.stamp"):
            p = flutter_root / "bin/cache" / snap
            if p.exists():
                p.unlink()
                print(f"[invalidated] {p}")
    return changed


def patch_engine_sources(flutter_root: Path, target_ios: str) -> int:
    # Support both monorepo layout (flutter_root/engine/src) and standalone gclient layout (src/)
    src = flutter_root / "engine/src"
    if not src.exists() and (flutter_root / "flutter/shell").exists():
        src = flutter_root

    if not src.exists():
        raise FileNotFoundError(f"Engine src directory not found under {flutter_root}")

    changed = 0

    # 1. darwin_sdk.gni: ios_deployment_target = "12.2"
    changed += int(
        edit_if_present(
            src / "build/config/darwin/darwin_sdk.gni",
            lambda t: re.sub(
                r'ios_deployment_target\s*=\s*"[0-9.]+"',
                f'ios_deployment_target = "{target_ios}"',
                t,
            ),
        )
    )

    # 2. build/config/compiler/BUILD.gn, build/config/darwin/BUILD.gn & ios/BUILD.gn:
    #    Disable -Werror / -fatal_warnings (Xcode 16 warns on -ld_classic and iOS 12 deprecations),
    #    inject -fno-aligned-allocation, -Wno-unguarded-availability-new, and -Wl,-ld_classic.
    changed += int(
        edit_if_present(
            src / "build/config/compiler/BUILD.gn",
            lambda t: t.replace('"-Werror",  # Warnings as errors.', '"-Wno-error",  # Warnings unlocked by oldcook.'),
        )
    )

    changed += int(
        edit_if_present(
            src / "flutter/shell/platform/darwin/ios/BUILD.gn",
            lambda t: re.sub(r'\s*"-Xlinker",\s*"-fatal_warnings",', "", t),
        )
    )

    def _fix_darwin_gn(text: str) -> str:
        if "OLDCOOK_IOS12_FLAGS" in text:
            return text
        inject = '''
  # OLDCOOK_IOS12_FLAGS
  if (is_ios) {
    cflags = [ "-Wno-unguarded-availability-new", "-Wno-deprecated-declarations", "-Wno-error" ]
    cflags_objc = [ "-Wno-unguarded-availability-new", "-Wno-deprecated-declarations", "-Wno-error" ]
    cflags_cc = [ "-fno-aligned-allocation", "-D_LIBCPP_AVAILABILITY_DISABLE", "-Wno-error" ]
    cflags_objcc = [
      "-fno-aligned-allocation",
      "-D_LIBCPP_AVAILABILITY_DISABLE",
      "-Wno-unguarded-availability-new",
      "-Wno-deprecated-declarations",
      "-Wno-error",
    ]
    ldflags = [
      "-Wl,-ld_classic",
      "-Wl,-weak_framework,UniformTypeIdentifiers",
      "-Wl,-weak_framework,LinkPresentation",
      "-Wl,-weak_framework,MetricKit",
    ]
  }
'''
        return re.sub(r'(config\("compiler"\)\s*\{)', r"\1" + inject, text, count=1)

    changed += int(edit_if_present(src / "build/config/darwin/BUILD.gn", _fix_darwin_gn))

    ios_dir = src / "flutter/shell/platform/darwin/ios"

    # 3. FlutterSceneDelegate.h & FlutterSceneLifeCycle.h: mark classes API_AVAILABLE(ios(13.0))
    def _guard_scene_delegate_h(text: str) -> str:
        if "API_AVAILABLE(ios(13.0))" in text:
            return text
        return text.replace(
            "FLUTTER_DARWIN_EXPORT\n@interface FlutterSceneDelegate",
            "FLUTTER_DARWIN_EXPORT\nAPI_AVAILABLE(ios(13.0))\n@interface FlutterSceneDelegate",
        )

    changed += int(
        edit_if_present(ios_dir / "framework/Headers/FlutterSceneDelegate.h", _guard_scene_delegate_h)
    )

    def _guard_scene_lifecycle_h(text: str) -> str:
        for tok in ("@interface FlutterPluginSceneLifeCycleDelegate", "@protocol FlutterSceneLifeCycleProvider"):
            if tok in text and f"API_AVAILABLE(ios(13.0))\n{tok}" not in text:
                text = text.replace(tok, f"API_AVAILABLE(ios(13.0))\n{tok}")
        return text

    changed += int(
        edit_if_present(ios_dir / "framework/Headers/FlutterSceneLifeCycle.h", _guard_scene_lifecycle_h)
    )

    # 4. FlutterEngine.mm: CRITICAL — UISceneWillConnectNotification is nil on iOS 12;
    #    passing name:nil to NSNotificationCenter subscribes to ALL notifications and crashes!
    def _fix_flutter_engine_mm(text: str) -> str:
        if "OLDCOOK_SCENE_GUARD" in text:
            return text
        target = """  [center addObserver:self
             selector:@selector(sceneWillConnect:)
                 name:UISceneWillConnectNotification
               object:nil];
  if (!FlutterSharedApplication.isAvailable) {
    [center addObserver:self
               selector:@selector(sceneWillEnterForeground:)
                   name:UISceneWillEnterForegroundNotification
                 object:nil];
    [center addObserver:self
               selector:@selector(sceneDidEnterBackground:)
                   name:UISceneDidEnterBackgroundNotification
                 object:nil];
    return;
  }"""
        repl = """  // OLDCOOK_SCENE_GUARD
  if (@available(iOS 13.0, *)) {
    [center addObserver:self
               selector:@selector(sceneWillConnect:)
                   name:UISceneWillConnectNotification
                 object:nil];
    if (!FlutterSharedApplication.isAvailable) {
      [center addObserver:self
                 selector:@selector(sceneWillEnterForeground:)
                     name:UISceneWillEnterForegroundNotification
                   object:nil];
      [center addObserver:self
                 selector:@selector(sceneDidEnterBackground:)
                     name:UISceneDidEnterBackgroundNotification
                   object:nil];
      return;
    }
  }"""
        return text.replace(target, repl, 1)

    changed += int(edit_if_present(ios_dir / "framework/Source/FlutterEngine.mm", _fix_flutter_engine_mm))

    # 5. FlutterMetalLayer.mm: CAFrameRateRangeMake is iOS 15.0+
    def _fix_metal_layer_mm(text: str) -> str:
        if "if (@available(iOS 15.0, *))" in text and "CAFrameRateRangeMake" in text:
            return text
        return re.sub(
            r"(_displayLink\.preferredFrameRateRange\s*=\s*\n?\s*CAFrameRateRangeMake\([^;]+;\s*)",
            r"if (@available(iOS 15.0, *)) {\n    \1  }\n",
            text,
            count=1,
        )

    changed += int(edit_if_present(ios_dir / "framework/Source/FlutterMetalLayer.mm", _fix_metal_layer_mm))

    # 6. FlutterPlatformViews.mm & FlutterPlatformViewsController.mm: cornerCurve / kCACornerCurve* (iOS 13.0+)
    def _fix_corner_curve(text: str) -> str:
        if "OLDCOOK_CORNER_CURVE" in text:
            return text
        return re.sub(
            r"(visualEffectView\.layer\.cornerCurve\s*=\s*\n?\s*[^;]+kCACornerCurveCircular;)",
            r"// OLDCOOK_CORNER_CURVE\n  if (@available(iOS 13.0, *)) {\n    \1\n  }",
            text,
        )

    changed += int(edit_if_present(ios_dir / "framework/Source/FlutterPlatformViews.mm", _fix_corner_curve))
    changed += int(
        edit_if_present(ios_dir / "framework/Source/FlutterPlatformViewsController.mm", _fix_corner_curve)
    )

    # 7. FlutterPluginAppLifeCycleDelegate.mm: eventAttribution (iOS 14.5+)
    def _fix_lifecycle_mm(text: str) -> str:
        if "OLDCOOK_EVENT_ATTR" in text:
            return text
        target = """  if (options.eventAttribution) {
    convertedOptions[UIApplicationOpenURLOptionsEventAttributionKey] = options.eventAttribution;
  }"""
        repl = """  // OLDCOOK_EVENT_ATTR
  if (@available(iOS 14.5, *)) {
    if (options.eventAttribution) {
      convertedOptions[UIApplicationOpenURLOptionsEventAttributionKey] = options.eventAttribution;
    }
  }"""
        return text.replace(target, repl, 1)

    changed += int(
        edit_if_present(ios_dir / "framework/Source/FlutterPluginAppLifeCycleDelegate.mm", _fix_lifecycle_mm)
    )

    # 8. SemanticsObject.mm: UIAccessibilitySpeechAttributeSpellOut (iOS 13.0+)
    def _fix_semantics_mm(text: str) -> str:
        if "OLDCOOK_SPELLOUT" in text:
            return text
        target = """      case flutter::StringAttributeType::kSpellOut: {
        NSDictionary* attributeDict = @{
          UIAccessibilitySpeechAttributeSpellOut : @YES,
        };
        [attributedString setAttributes:attributeDict range:range];
        break;
      }"""
        repl = """      case flutter::StringAttributeType::kSpellOut: {
        // OLDCOOK_SPELLOUT
        if (@available(iOS 13.0, *)) {
          NSDictionary* attributeDict = @{
            UIAccessibilitySpeechAttributeSpellOut : @YES,
          };
          [attributedString setAttributes:attributeDict range:range];
        }
        break;
      }"""
        return text.replace(target, repl, 1)

    changed += int(edit_if_present(ios_dir / "framework/Source/SemanticsObject.mm", _fix_semantics_mm))

    # 9. FlutterTextInputPlugin.mm: mark iOS 16 UIMenu/UICommand helpers API_AVAILABLE(ios(16.0))
    def _fix_text_input_mm(text: str) -> str:
        text = text.replace(
            "                        suggestedMenu:(UIMenu*)suggestedMenu {",
            "                        suggestedMenu:(UIMenu*)suggestedMenu API_AVAILABLE(ios(16.0)) {",
        )
        text = text.replace(
            "                             encodedItem:(NSDictionary<NSString*, id>*)encodedItem {",
            "                             encodedItem:(NSDictionary<NSString*, id>*)encodedItem API_AVAILABLE(ios(16.0)) {",
        )
        return text

    changed += int(
        edit_if_present(ios_dir / "framework/Source/FlutterTextInputPlugin.mm", _fix_text_input_mm)
    )

    # 10. AccessibilityFeatures.swift: guard iOS 13.0+ onOffSwitchLabels & videoAutoplay APIs
    def _fix_a11y_swift(text: str) -> str:
        if "OLDCOOK_A11Y_IOS12" in text:
            return text
        text = text.replace(
            """            AccessibilityFeatures.darkerSystemColorsStatusDidChangeNotification,
            AccessibilityFeatures.onOffSwitchLabelsDidChangeNotification,
            AccessibilityFeatures.videosAutoPlayStatusDidChangeNotification,
        ]""",
            """            // OLDCOOK_A11Y_IOS12
            AccessibilityFeatures.darkerSystemColorsStatusDidChangeNotification,
        ]
        if #available(iOS 13.0, *) {
            names.append(contentsOf: [
                AccessibilityFeatures.onOffSwitchLabelsDidChangeNotification,
                AccessibilityFeatures.videosAutoPlayStatusDidChangeNotification,
            ])
        }""",
        )
        text = text.replace(
            "return UIAccessibility.onOffSwitchLabelsDidChangeNotification.rawValue",
            "if #available(iOS 13.0, *) { return UIAccessibility.onOffSwitchLabelsDidChangeNotification.rawValue }\n        return \"\"",
        )
        text = text.replace(
            "return UIAccessibility.isOnOffSwitchLabelsEnabled",
            "if #available(iOS 13.0, *) { return UIAccessibility.isOnOffSwitchLabelsEnabled }\n        return false",
        )
        text = text.replace(
            "return UIAccessibility.videoAutoplayStatusDidChangeNotification.rawValue",
            "if #available(iOS 13.0, *) { return UIAccessibility.videoAutoplayStatusDidChangeNotification.rawValue }\n        return \"\"",
        )
        text = text.replace(
            "return UIAccessibility.isVideoAutoplayEnabled",
            "if #available(iOS 13.0, *) { return UIAccessibility.isVideoAutoplayEnabled }\n        return true",
        )
        return text

    changed += int(
        edit_if_present(ios_dir / "framework/Source/AccessibilityFeatures.swift", _fix_a11y_swift)
    )

    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flutter-root", type=Path, required=True, help="Root of Flutter SDK or engine checkout")
    ap.add_argument("--mode", choices=("tools-only", "full"), default="tools-only")
    ap.add_argument("--target-ios", default="12.2", help="Minimum iOS version (default: 12.2 for Swift ABI)")
    args = ap.parse_args()

    total = 0
    if (args.flutter_root / "packages/flutter_tools").exists():
        total += patch_flutter_tools(args.flutter_root, args.target_ios)
    if args.mode == "full":
        total += patch_engine_sources(args.flutter_root, args.target_ios)

    print(f"[done] patch_flutter_ios12 ({args.mode}): {total} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
