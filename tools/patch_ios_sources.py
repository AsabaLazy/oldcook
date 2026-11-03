#!/usr/bin/env python3
"""Post-`pub get` semantic iOS 12 source patcher for Runner & native Flutter plugins.

Runs inside a prepared recipe workspace (`work/<recipe>`) AFTER `flutter pub get`:
1. Guards `ios/Runner/SceneDelegate.swift` with `@available(iOS 13.0, *)`.
2. Scans `.dart_tool/package_config.json` for plugins containing `ios/` or `darwin/` native code.
3. Vendors only plugins needing iOS 12 fixes into `<workspace>/.oldcook_plugins/<pkg>` (never
   mutating global `~/.pub-cache`), lowers `.podspec` & `Package.swift` floors to `12.2`, guards
   `FlutterSceneLifeCycleDelegate` / `addSceneDelegate`, injects `file_picker_darwin` iOS 12
   fallback picker, and registers `.oldcook_plugins/<pkg>` in `pubspec.yaml` `dependency_overrides`.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


LEGACY_IOS12_FILE_PICKER_SWIFT = """#if os(iOS)
import Flutter
import Foundation
import MobileCoreServices
import UIKit

final class IOS12LegacyFilePickerHandler: NSObject,
    FlutterStreamHandler,
    UIDocumentPickerDelegate,
    UIImagePickerControllerDelegate,
    UINavigationControllerDelegate {

    private weak var registrar: FlutterPluginRegistrar?
    private var pendingResult: FlutterResult?
    private var eventSink: FlutterEventSink?

    init(registrar: FlutterPluginRegistrar) {
        self.registrar = registrar
    }

    func onListen(withArguments _: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        eventSink = events
        return nil
    }

    func onCancel(withArguments _: Any?) -> FlutterError? {
        eventSink = nil
        return nil
    }

    private func topVC() -> UIViewController? {
        var vc = UIApplication.shared.keyWindow?.rootViewController
        while let presented = vc?.presentedViewController {
            vc = presented
        }
        return vc
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        if call.method == "clear" {
            result(true)
            return
        }
        guard pendingResult == nil else {
            result(FlutterError(code: "multiple_request", message: "Cancelled", details: nil))
            return
        }
        pendingResult = result
        let args = call.arguments as? [String: Any] ?? [:]
        let multi = (args["allowMultipleSelection"] as? Bool) ?? false

        switch call.method {
        case "image", "video", "media":
            let picker = UIImagePickerController()
            picker.delegate = self
            picker.sourceType = .photoLibrary
            if call.method == "video" {
                picker.mediaTypes = [kUTTypeMovie as String]
            } else if call.method == "media" {
                picker.mediaTypes = [kUTTypeImage as String, kUTTypeMovie as String]
            } else {
                picker.mediaTypes = [kUTTypeImage as String]
            }
            topVC()?.present(picker, animated: true)
        default:
            let picker = UIDocumentPickerViewController(documentTypes: ["public.item"], in: .import)
            picker.delegate = self
            picker.allowsMultipleSelection = multi
            topVC()?.present(picker, animated: true)
        }
    }

    private func packURL(_ url: URL) -> [String: Any]? {
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
        return ["path": url.path, "name": url.lastPathComponent, "size": size]
    }

    func documentPickerWasCancelled(_: UIDocumentPickerViewController) {
        pendingResult?(nil)
        pendingResult = nil
    }

    func documentPicker(_: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        let items = urls.compactMap { packURL($0) }
        pendingResult?(items.isEmpty ? nil : items)
        pendingResult = nil
    }

    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
        picker.dismiss(animated: true)
        pendingResult?(nil)
        pendingResult = nil
    }

    func imagePickerController(_ picker: UIImagePickerController,
                               didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
        picker.dismiss(animated: true)
        if let url = info[.imageURL] as? URL ?? info[.mediaURL] as? URL, let item = packURL(url) {
            pendingResult?([item])
        } else if let img = info[.originalImage] as? UIImage, let data = img.jpegData(compressionQuality: 0.9) {
            let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("picked_\\( Int(Date().timeIntervalSince1970) ).jpg")
            try? data.write(to: tmp)
            pendingResult?(packURL(tmp).map { [$0] })
        } else {
            pendingResult?(nil)
        }
        pendingResult = nil
    }
}
#endif
"""


def ver_gt(ver: str, ceiling: str) -> bool:
    t1 = tuple(int(x) for x in ver.split(".") if x.isdigit())
    t2 = tuple(int(x) for x in ceiling.split(".") if x.isdigit())
    return t1 > t2


def patch_runner_swift(work_dir: Path) -> None:
    scene_swift = work_dir / "ios/Runner/SceneDelegate.swift"
    if not scene_swift.exists():
        return
    text = scene_swift.read_text(encoding="utf-8")
    if "@available(iOS 13.0, *)\nclass SceneDelegate" not in text and "class SceneDelegate" in text:
        text = text.replace("class SceneDelegate", "@available(iOS 13.0, *)\nclass SceneDelegate", 1)
        scene_swift.write_text(text, encoding="utf-8")
        print(f"[patched] {scene_swift.relative_to(work_dir)}")


def resolve_pkg_root(root_uri: str, cfg_dir: Path) -> Path:
    if root_uri.startswith("file://"):
        parsed = urlparse(root_uri)
        return Path(unquote(parsed.path)).resolve()
    return (cfg_dir / root_uri).resolve()


def needs_plugin_patch(pkg_dir: Path, min_ios: str) -> bool:
    for sub in ("ios", "darwin"):
        d = pkg_dir / sub
        if not d.exists():
            continue
        for podspec in d.glob("*.podspec"):
            txt = podspec.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"(?:ios\.deployment_target|platform\s*=?\s*:ios\s*,)\s*['\"]([0-9.]+)['\"]", txt):
                if ver_gt(m.group(1), min_ios):
                    return True
        for pkg_swift in d.rglob("Package.swift"):
            txt = pkg_swift.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"\.iOS\(\s*(?:['\"]([0-9.]+)['\"]|\.v(\d+))\s*\)", txt):
                ver = m.group(1) or f"{m.group(2)}.0"
                if ver_gt(ver, min_ios):
                    return True
        for swift_f in d.rglob("*.swift"):
            txt = swift_f.read_text(encoding="utf-8", errors="ignore")
            if "addSceneDelegate(" in txt or "FlutterSceneLifeCycleDelegate" in txt:
                return True
    return False


def transform_vendored_plugin(pkg_name: str, dst: Path, min_ios: str) -> None:
    # 0. Strip Dart pub workspace resolution directive if copied out of a git monorepo
    v_pub = dst / "pubspec.yaml"
    if v_pub.exists():
        ptxt = re.sub(r"^\s*resolution\s*:\s*workspace\s*\n?", "", v_pub.read_text(encoding="utf-8"), flags=re.M)
        v_pub.write_text(ptxt, encoding="utf-8")

    # 1. Lower all podspecs & add C++17 availability bypass
    for podspec in list(dst.glob("ios/*.podspec")) + list(dst.glob("darwin/*.podspec")):
        txt = podspec.read_text(encoding="utf-8")
        txt = re.sub(
            r"(ios\.deployment_target\s*=\s*)['\"][0-9.]+['\"]",
            rf"\g<1>'{min_ios}'",
            txt,
        )
        txt = re.sub(
            r"(platform\s*=\s*:ios\s*,\s*)['\"][0-9.]+['\"]",
            rf"\g<1>'{min_ios}'",
            txt,
        )
        podspec.write_text(txt, encoding="utf-8")

    # 2. Lower all SwiftPM Package.swift iOS floors
    for pkg_swift in list(dst.rglob("Package.swift")):
        txt = pkg_swift.read_text(encoding="utf-8")
        txt = re.sub(r"\.iOS\(\s*['\"][0-9.]+['\"]\s*\)", '.iOS("12.0")', txt)
        txt = re.sub(r"\.iOS\(\s*\.v(?:1[3-9]|[2-9]\d)\s*\)", ".iOS(.v12)", txt)
        pkg_swift.write_text(txt, encoding="utf-8")

    # 3. Generic Swift FlutterSceneLifeCycleDelegate & registrar.addSceneDelegate guards
    for swift_f in list(dst.glob("ios/**/*.swift")) + list(dst.glob("darwin/**/*.swift")):
        txt = swift_f.read_text(encoding="utf-8")
        orig = txt
        if "addSceneDelegate(" in txt and "if #available(iOS 13.0, *)" not in txt:
            txt = re.sub(
                r"^(\s*)(registrar\.addSceneDelegate\([^)]+\))",
                r"\1if #available(iOS 13.0, *) { \2 }",
                txt,
                flags=re.M,
            )
        if "extension " in txt and ": FlutterSceneLifeCycleDelegate" in txt:
            txt = re.sub(
                r"(?<!@available\(iOS 13\.0, \*\)\n)^(extension\s+\w+\s*:\s*FlutterSceneLifeCycleDelegate)",
                r"@available(iOS 13.0, *)\n\1",
                txt,
                flags=re.M,
            )
        if txt != orig:
            swift_f.write_text(txt, encoding="utf-8")

    # 4. Package-specific surgical transforms
    if pkg_name == "share_plus":
        m_file = dst / "ios/share_plus/Sources/share_plus/FPPSharePlusPlugin.m"
        if m_file.exists():
            mtxt = m_file.read_text(encoding="utf-8")
            if "OLDCOOK_SHARE_IOS12" not in mtxt:
                mtxt = mtxt.replace(
                    "  NSSet *scenes = [[UIApplication sharedApplication] connectedScenes];",
                    "  // OLDCOOK_SHARE_IOS12\n  if (@available(iOS 13.0, *)) {\n  NSSet *scenes = [[UIApplication sharedApplication] connectedScenes];",
                    1,
                )
                mtxt = mtxt.replace(
                    "  return nil;\n}",
                    "  }\n  return [UIApplication sharedApplication].keyWindow.rootViewController;\n}",
                    1,
                )
                m_file.write_text(mtxt, encoding="utf-8")

    if pkg_name == "file_picker_darwin":
        src_dir = dst / "darwin/file_picker_darwin/Sources/file_picker_darwin"
        ios_handler = src_dir / "IOSFilePickerHandler.swift"
        plugin_swift = src_dir / "FilePickerPlugin.swift"
        if ios_handler.exists() and plugin_swift.exists():
            htxt = ios_handler.read_text(encoding="utf-8")
            if "@available(iOS 14.0, *)\nfinal class IOSFilePickerHandler" not in htxt:
                htxt = htxt.replace(
                    "final class IOSFilePickerHandler",
                    "@available(iOS 14.0, *)\nfinal class IOSFilePickerHandler",
                    1,
                )
                ios_handler.write_text(htxt, encoding="utf-8")
            (src_dir / "IOS12LegacyFilePickerHandler.swift").write_text(
                LEGACY_IOS12_FILE_PICKER_SWIFT, encoding="utf-8"
            )
            plugin_swift.write_text(
                """#if os(iOS)
import Flutter
#elseif os(macOS) && canImport(FlutterMacOS)
import FlutterMacOS
#endif
import Foundation

#if os(iOS) || (os(macOS) && canImport(FlutterMacOS))
public class FilePickerPlugin: NSObject, FlutterPlugin {
    #if os(iOS)
    private let streamHandler: NSObject & FlutterStreamHandler
    private let callDispatcher: (FlutterMethodCall, @escaping FlutterResult) -> Void
    #else
    private let handler: MacOSFilePickerHandler
    #endif

    init(registrar: FlutterPluginRegistrar) {
        #if os(iOS)
        if #available(iOS 14.0, *) {
            let h = IOSFilePickerHandler(registrar: registrar)
            streamHandler = h
            callDispatcher = { call, res in h.handle(call, result: res) }
        } else {
            let h = IOS12LegacyFilePickerHandler(registrar: registrar)
            streamHandler = h
            callDispatcher = { call, res in h.handle(call, result: res) }
        }
        #else
        handler = MacOSFilePickerHandler(registrar: registrar)
        #endif
        super.init()
    }

    public static func register(with registrar: FlutterPluginRegistrar) {
        #if os(iOS)
        let messenger = registrar.messenger()
        #else
        let messenger = registrar.messenger
        #endif
        let channel = FlutterMethodChannel(name: "miguelruivo.flutter.plugins.filepicker", binaryMessenger: messenger)
        let eventChannel = FlutterEventChannel(name: "miguelruivo.flutter.plugins.filepickerevent", binaryMessenger: messenger)
        let instance = FilePickerPlugin(registrar: registrar)
        registrar.addMethodCallDelegate(instance, channel: channel)
        #if os(iOS)
        eventChannel.setStreamHandler(instance.streamHandler)
        if #available(iOS 13.0, *) { registrar.addSceneDelegate(instance) }
        #else
        eventChannel.setStreamHandler(instance.handler)
        #endif
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        #if os(iOS)
        callDispatcher(call, result)
        #else
        handler.handle(call, result: result)
        #endif
    }
}

#if os(iOS)
@available(iOS 13.0, *)
extension FilePickerPlugin: FlutterSceneLifeCycleDelegate {}
#endif
#endif
""",
                encoding="utf-8",
            )


def append_pubspec_overrides(pubspec: Path, vendored_names: list[str]) -> None:
    if not vendored_names or not pubspec.exists():
        return
    text = pubspec.read_text(encoding="utf-8")
    text = re.sub(
        r"\n?[ \t]*# BEGIN OLDCOOK VENDORED PLUGINS.*?# END OLDCOOK VENDORED PLUGINS\n?",
        "\n",
        text,
        flags=re.S,
    )

    m_sec = re.search(r"^dependency_overrides\s*:\s*$", text, re.M)
    if m_sec:
        after_start = m_sec.end()
        m_next = re.search(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", text[after_start:], re.M)
        sec_end = after_start + m_next.start() if m_next else len(text)
        sec_body = text[after_start:sec_end]

        lines = ["  # BEGIN OLDCOOK VENDORED PLUGINS"]
        for name in sorted(vendored_names):
            if re.search(rf"^\s{{2}}{re.escape(name)}\s*:", sec_body, re.M):
                continue
            lines.append(f"  {name}:")
            lines.append(f"    path: .oldcook_plugins/{name}")
        lines.append("  # END OLDCOOK VENDORED PLUGINS")

        if len(lines) > 2:
            block = "\n" + "\n".join(lines) + "\n"
            updated = text[:sec_end].rstrip("\n") + block + ("\n" + text[sec_end:].lstrip("\n") if sec_end < len(text) else "")
            pubspec.write_text(updated, encoding="utf-8")
    else:
        lines = ["\n# BEGIN OLDCOOK VENDORED PLUGINS", "dependency_overrides:"]
        for name in sorted(vendored_names):
            lines.append(f"  {name}:")
            lines.append(f"    path: .oldcook_plugins/{name}")
        lines.append("# END OLDCOOK VENDORED PLUGINS\n")
        pubspec.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def stub_skipped_ios_native_asset(dst: Path) -> None:
    for hook_rel in ("hook/build.dart", "build.dart"):
        hook = dst / hook_rel
        if hook.exists():
            txt = hook.read_text(encoding="utf-8")
            if "OLDCOOK_SKIP_IOS_ASSET" not in txt:
                txt = re.sub(
                    r"(build\s*\([^)]*\)\s*async\s*\{)",
                    r"\1\n    // OLDCOOK_SKIP_IOS_ASSET\n    if (input.config.buildCodeAssets && input.config.code.targetOS.name == 'iOS') { return; }",
                    txt,
                    count=1,
                )
                hook.write_text(txt, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workspace", type=Path, help="Path to recipe workspace (e.g. work/piliplus)")
    ap.add_argument("--min-ios", default="12.2", help="Target iOS deployment floor (default: 12.2)")
    ap.add_argument("--recipe-json", type=Path, help="Optional recipe.json for skip_ios_native_assets")
    args = ap.parse_args()

    ws = args.workspace.resolve()
    patch_runner_swift(ws)

    skip_assets: set[str] = set()
    recipe_json = args.recipe_json or (Path(__file__).resolve().parent.parent / "recipes" / ws.name / "recipe.json")
    if recipe_json.exists():
        rcfg = json.loads(recipe_json.read_text(encoding="utf-8"))
        skip_assets = set(rcfg.get("skip_ios_native_assets", []))

    pkg_cfg = ws / ".dart_tool/package_config.json"
    if not pkg_cfg.exists():
        print(f"[info] {pkg_cfg} not found yet (run `flutter pub get` first to vendor plugins).")
        return 0

    cfg = json.loads(pkg_cfg.read_text(encoding="utf-8"))
    vendor_root = ws / ".oldcook_plugins"
    vendored: list[str] = []

    for pkg in cfg.get("packages", []):
        name = pkg["name"]
        src_dir = resolve_pkg_root(pkg["rootUri"], pkg_cfg.parent)
        if not src_dir.exists() or src_dir.is_relative_to(ws):
            continue
        if name in skip_assets or needs_plugin_patch(src_dir, args.min_ios):
            dst = vendor_root / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src_dir, dst, symlinks=True)
            if name in skip_assets:
                stub_skipped_ios_native_asset(dst)
            if needs_plugin_patch(dst, args.min_ios):
                transform_vendored_plugin(name, dst, args.min_ios)
            vendored.append(name)
            print(f"[vendored+patched] {name} -> .oldcook_plugins/{name}")

    append_pubspec_overrides(ws / "pubspec.yaml", vendored)
    print(f"[done] Patched Runner + {len(vendored)} native plugin(s) for iOS {args.min_ios}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
