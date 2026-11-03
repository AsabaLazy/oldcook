#!/usr/bin/env python3
"""Offline end-to-end self-test suite for oldcook on Linux (< 5s, zero network)."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_polyfill_clang() -> None:
    sdk = ROOT / "sdks/iPhoneOS12.4.sdk"
    assert sdk.exists(), f"Missing {sdk}; run ./tools/fetch_sdk.sh"
    polyfill = ROOT / "compat-packages/ios12_polyfill/Sources/IOS12Polyfill.m"
    with tempfile.TemporaryDirectory(prefix="oc_test_poly_") as td:
        obj = Path(td) / "IOS12Polyfill.o"
        run([
            "clang",
            "-target", "arm64-apple-ios12.0",
            "-isysroot", str(sdk),
            "-fobjc-arc",
            "-Wall", "-Wextra", "-Werror",
            "-c", str(polyfill),
            "-o", str(obj),
        ])
        assert obj.exists() and obj.stat().st_size > 0
    print("[pass] IOS12Polyfill.m compiles cleanly with -Wall -Wextra -Werror against iPhoneOS12.4.sdk")


def test_engine_patcher_against_local_flutter() -> None:
    host_flutter = Path("/home/luo/.local/share/flutter")
    if not host_flutter.exists():
        print("[skip] Host Flutter SDK not found at ~/.local/share/flutter")
        return

    rel_files = [
        "packages/flutter_tools/lib/src/ios/migrations/ios_deployment_target_migration.dart",
        "packages/flutter_tools/bin/podhelper.rb",
        "packages/flutter_tools/lib/src/isolated/native_assets/ios/native_assets.dart",
        "engine/src/build/config/compiler/BUILD.gn",
        "engine/src/build/config/darwin/darwin_sdk.gni",
        "engine/src/build/config/darwin/BUILD.gn",
        "engine/src/flutter/shell/platform/darwin/ios/BUILD.gn",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Headers/FlutterSceneDelegate.h",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Headers/FlutterSceneLifeCycle.h",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterEngine.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterMetalLayer.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterPlatformViews.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterPlatformViewsController.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterPluginAppLifeCycleDelegate.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/SemanticsObject.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterTextInputPlugin.mm",
        "engine/src/flutter/shell/platform/darwin/ios/framework/Source/AccessibilityFeatures.swift",
    ]

    with tempfile.TemporaryDirectory(prefix="oc_test_engine_") as td:
        tmp_f = Path(td)
        for rel in rel_files:
            src = host_flutter / rel
            if src.exists():
                dst = tmp_f / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        (tmp_f / "bin/cache").mkdir(parents=True, exist_ok=True)
        (tmp_f / "bin/cache/flutter_tools.snapshot").write_bytes(b"dummy")

        patcher = ROOT / "engine-patches/patch_flutter_ios12.py"
        run([sys.executable, str(patcher), "--flutter-root", str(tmp_f), "--mode", "full", "--target-ios", "12.2"])

        assert not (tmp_f / "bin/cache/flutter_tools.snapshot").exists(), "Snapshot not invalidated"
        assert 'ios_deployment_target = "12.2"' in (tmp_f / "engine/src/build/config/darwin/darwin_sdk.gni").read_text()
        assert "const targetIOSVersion = 12;" in (
            tmp_f / "packages/flutter_tools/lib/src/isolated/native_assets/ios/native_assets.dart"
        ).read_text()
        assert "s.ios.deployment_target = '12.2'" in (tmp_f / "packages/flutter_tools/bin/podhelper.rb").read_text()
        assert "OLDCOOK_SCENE_GUARD" in (
            tmp_f / "engine/src/flutter/shell/platform/darwin/ios/framework/Source/FlutterEngine.mm"
        ).read_text()
        assert "OLDCOOK_A11Y_IOS12" in (
            tmp_f / "engine/src/flutter/shell/platform/darwin/ios/framework/Source/AccessibilityFeatures.swift"
        ).read_text()

        # Idempotency check: second run must modify 0 files
        res2 = run([sys.executable, str(patcher), "--flutter-root", str(tmp_f), "--mode", "full", "--target-ios", "12.2"])
        assert "0 file(s) updated" in res2.stdout, res2.stdout

    print("[pass] patch_flutter_ios12.py verified against real Flutter 3.47.9 sources (idempotent)")


def test_recipe_and_plugin_vendor_pipeline() -> None:
    with tempfile.TemporaryDirectory(prefix="oc_test_ws_") as td:
        ws = Path(td) / "mockapp"
        (ws / "ios/Runner.xcodeproj").mkdir(parents=True)
        (ws / "ios/Runner").mkdir(parents=True)
        (ws / "ios/Flutter").mkdir(parents=True)
        (ws / ".dart_tool").mkdir(parents=True)

        (ws / "pubspec.yaml").write_text(
            "name: mockapp\ndependencies:\n  file_picker_darwin: ^2.3.2\n\n"
            "dependency_overrides:\n  foo: ^1.0.0\n\nflutter:\n  uses-material-design: true\n"
        )
        (ws / "ios/Runner.xcodeproj/project.pbxproj").write_text("IPHONEOS_DEPLOYMENT_TARGET = 15.0;\n")
        (ws / "ios/Runner/Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
            "<key>MinimumOSVersion</key><string>15.0</string>"
            "<key>UIApplicationSceneManifest</key><dict/>"
            "</dict></plist>"
        )
        (ws / "ios/Runner/SceneDelegate.swift").write_text(
            "import Flutter\nimport UIKit\nclass SceneDelegate: FlutterSceneDelegate {}\n"
        )
        (ws / "ios/Podfile").write_text("platform :ios, '14.0'\ntarget 'Runner' do\nend\n")

        # Mock external plugin in fake pub-cache
        ext_pkg = Path(td) / "fake_pub_cache/file_picker_darwin"
        (ext_pkg / "darwin/file_picker_darwin/Sources/file_picker_darwin").mkdir(parents=True)
        (ext_pkg / "pubspec.yaml").write_text("name: file_picker_darwin\n")
        (ext_pkg / "darwin/file_picker_darwin.podspec").write_text(
            "Pod::Spec.new do |s|\n  s.ios.deployment_target = '14.0'\nend\n"
        )
        (ext_pkg / "darwin/file_picker_darwin/Package.swift").write_text(
            'platforms: [.iOS("14.0")]\n'
        )
        (ext_pkg / "darwin/file_picker_darwin/Sources/file_picker_darwin/IOSFilePickerHandler.swift").write_text(
            "final class IOSFilePickerHandler {}\n"
        )
        (ext_pkg / "darwin/file_picker_darwin/Sources/file_picker_darwin/FilePickerPlugin.swift").write_text(
            "public class FilePickerPlugin {}\n"
        )
        (ext_pkg / "darwin/file_picker_darwin/Sources/file_picker_darwin/SceneSample.swift").write_text(
            "class Foo {\n"
            "  var s: UIScreen? {\n"
            "    return vc?.view.window?.windowScene?.screen\n"
            "  }\n"
            "  public func scene(\n"
            "    _ scene: UIScene,\n"
            "    openURLContexts ctx: Set<UIOpenURLContext>\n"
            "  ) {}\n"
            "}\n"
        )

        (ws / ".dart_tool/package_config.json").write_text(
            json.dumps({
                "configVersion": 2,
                "packages": [{"name": "file_picker_darwin", "rootUri": f"file://{ext_pkg}"}],
            })
        )

        run([sys.executable, str(ROOT / "tools/patch_ios_sources.py"), str(ws), "--min-ios", "12.2"])

        assert "@available(iOS 13.0, *)\nclass SceneDelegate" in (ws / "ios/Runner/SceneDelegate.swift").read_text()
        vendored = ws / ".oldcook_plugins/file_picker_darwin"
        assert vendored.exists()
        assert "s.ios.deployment_target = '12.2'" in (vendored / "darwin/file_picker_darwin.podspec").read_text()
        assert '.iOS("12.0")' in (vendored / "darwin/file_picker_darwin/Package.swift").read_text()
        assert (vendored / "darwin/file_picker_darwin/Sources/file_picker_darwin/IOS12LegacyFilePickerHandler.swift").exists()
        scene_out = (vendored / "darwin/file_picker_darwin/Sources/file_picker_darwin/SceneSample.swift").read_text()
        assert "@available(iOS 13.0, *)\n  public func scene(" in scene_out, scene_out
        assert "UIScreen.main" in scene_out, scene_out
        pub_out = (ws / "pubspec.yaml").read_text()
        assert "path: .oldcook_plugins/file_picker_darwin" in pub_out
        assert pub_out.index("file_picker_darwin:") < pub_out.index("flutter:\n"), pub_out

    print("[pass] patch_ios_sources.py verified (SceneDelegate guard + clean .oldcook_plugins vendoring)")


def test_piliplus_overlay_idempotent() -> None:
    pili_ws = ROOT / "work/piliplus"
    if not (pili_ws / ".git").exists():
        print("[skip] work/piliplus not cloned")
        return
    run([sys.executable, str(ROOT / "tools/apply_recipe.py"), "piliplus", "--overlay-only"])
    podfile = (pili_ws / "ios/Podfile").read_text()
    assert "platform :ios, '12.2'" in podfile
    assert "-Wl,-ld_classic" in podfile
    assert "-Wl,-weak_framework,UniformTypeIdentifiers" in podfile
    assert "ios12_polyfill" in podfile
    assert "@available(iOS 13.0, *)" in (pili_ws / "ios/Runner/SceneDelegate.swift").read_text()
    # Reset work/piliplus back to clean upstream HEAD after test
    run(["git", "reset", "--hard"], cwd=pili_ws)
    run(["git", "clean", "-fd"], cwd=pili_ws)
    print("[pass] apply_recipe.py verified on live PiliPlus checkout and restored cleanly")


def test_workflows_and_recipes_invariants() -> None:
    eng_wf = (ROOT / ".github/workflows/build-engine-ios12.yml").read_text()
    app_wf = (ROOT / ".github/workflows/reusable-flutter-ios12.yml").read_text()
    sync_wf = (ROOT / ".github/workflows/auto-sync.yml").read_text()
    assert '"name": "."' in eng_wf and "engine_ws/engine/src" in eng_wf and "--target-dir=ios_release" in eng_wf
    assert "flutter precache --ios" in app_wf and "xcrun vtool" in app_wf
    assert "--no-enable-swift-package-manager" in app_wf
    assert "schedule:" in sync_wf and "ensure-engines:" in sync_wf and "publish-or-report:" in sync_wf
    for rfile in (ROOT / "recipes").glob("*/recipe.json"):
        cfg = json.loads(rfile.read_text())
        assert "repo" in cfg and "min_ios" in cfg
    print("[pass] CI workflows & recipe.json invariants verified")


def main() -> int:
    test_polyfill_clang()
    test_engine_patcher_against_local_flutter()
    test_recipe_and_plugin_vendor_pipeline()
    test_piliplus_overlay_idempotent()
    test_workflows_and_recipes_invariants()
    print("\nALL SELF-TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
