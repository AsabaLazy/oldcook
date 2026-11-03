#!/usr/bin/env python3
"""Apply an overlay backport recipe onto an upstream checkout in work/<name>."""

import argparse
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WEAK_IOS13_FRAMEWORKS = [
    "AVFAudio",
    "CoreHaptics",
    "CryptoKit",
    "LinkPresentation",
    "MetricKit",
    "PhotosUI",
    "UniformTypeIdentifiers",
    "VisionKit",
]

WEAK_SWIFT_OVERLAYS = [
    "swiftUniformTypeIdentifiers",
    "swiftPhotosUI",
    "swiftNetwork",
    "swiftWebKit",
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def sync_upstream(repo_url: str, ref: str, dest: Path, shallow: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        cmd = ["git", "clone"]
        if shallow:
            cmd += ["--depth", "1", "--branch", ref]
        cmd += [repo_url, str(dest)]
        run(cmd)
        if not shallow:
            run(["git", "checkout", ref], cwd=dest)
    else:
        run(["git", "reset", "--hard"], cwd=dest)
        run(["git", "clean", "-fd"], cwd=dest)
        if shallow:
            run(["git", "fetch", "--depth", "1", "origin", ref], cwd=dest)
            run(["git", "checkout", "-B", "oldcook-target", "FETCH_HEAD"], cwd=dest)
        else:
            run(["git", "fetch", "--tags", "origin"], cwd=dest)
            run(["git", "checkout", ref], cwd=dest)


def patch_pbxproj(pbxproj: Path, min_ios: str) -> None:
    if not pbxproj.exists():
        return
    text = pbxproj.read_text(encoding="utf-8")
    updated = re.sub(
        r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*[0-9.]+;",
        f"IPHONEOS_DEPLOYMENT_TARGET = {min_ios};",
        text,
    )
    pbxproj.write_text(updated, encoding="utf-8")
    print(f"[ok] Patched {pbxproj.name} -> IPHONEOS_DEPLOYMENT_TARGET = {min_ios}")


def patch_plist(plist_path: Path, min_ios: str, strip_scene: bool) -> None:
    if not plist_path.exists():
        return
    with plist_path.open("rb") as f:
        data = plistlib.load(f)
    if "MinimumOSVersion" in data:
        data["MinimumOSVersion"] = min_ios
    if strip_scene and "UIApplicationSceneManifest" in data:
        del data["UIApplicationSceneManifest"]
    with plist_path.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_XML, sort_keys=False)
    print(f"[ok] Patched {plist_path.name} (MinimumOSVersion={min_ios})")


def patch_scene_delegate(ios_dir: Path) -> None:
    scene_swift = ios_dir / "Runner/SceneDelegate.swift"
    if not scene_swift.exists():
        return
    clean_scene = (
        "import Flutter\n"
        "import UIKit\n\n"
        "@available(iOS 13.0, *)\n"
        "class SceneDelegate: FlutterSceneDelegate {}\n"
    )
    if scene_swift.read_text(encoding="utf-8") != clean_scene:
        scene_swift.write_text(clean_scene, encoding="utf-8")
        print("[ok] Replaced ios/Runner/SceneDelegate.swift with SDK-universal @available(iOS 13.0, *) stub")


def patch_podfile(podfile: Path, min_ios: str, polyfill_rel: str, weak_fws: list[str]) -> None:
    if not podfile.exists():
        return
    text = podfile.read_text(encoding="utf-8")
    if re.search(r"^\s*#?\s*platform\s+:ios\s*,", text, flags=re.M):
        text = re.sub(
            r"^\s*#?\s*platform\s+:ios\s*,\s*['\"][0-9.]+['\"]",
            f"platform :ios, '{min_ios}'",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = f"platform :ios, '{min_ios}'\n" + text

    polyfill_line = f"  pod 'ios12_polyfill', :path => '{polyfill_rel}'\n"
    if "ios12_polyfill" not in text:
        text = re.sub(
            r"(target\s+['\"]Runner['\"]\s+do\s*\n)",
            r"\1" + polyfill_line,
            text,
            count=1,
        )

    ld_items = (
        ["-Wl,-ld_classic"]
        + [f"-Wl,-weak_framework,{fw}" for fw in weak_fws]
        + [f"-Wl,-weak-l{sw}" for sw in WEAK_SWIFT_OVERLAYS]
    )
    ld_ruby_list = ", ".join(repr(x) for x in ld_items)

    hook = f"""
# BEGIN OLDCOOK IOS12 HOOK
  installer.pods_project.targets.each do |oc_target|
    oc_target.build_configurations.each do |oc_config|
      oc_config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '{min_ios}'
      oc_config.build_settings['GCC_TREAT_WARNINGS_AS_ERRORS'] = 'NO'
      oc_config.build_settings['SWIFT_TREAT_WARNINGS_AS_ERRORS'] = 'NO'

      oc_cflags = oc_config.build_settings['OTHER_CFLAGS'] || ['$(inherited)']
      oc_cflags = [oc_cflags] if oc_cflags.is_a?(String)
      oc_cflags << '-Wno-unguarded-availability-new' unless oc_cflags.include?('-Wno-unguarded-availability-new')
      oc_config.build_settings['OTHER_CFLAGS'] = oc_cflags

      oc_cxxflags = oc_config.build_settings['OTHER_CPLUSPLUSFLAGS'] || ['$(inherited)']
      oc_cxxflags = [oc_cxxflags] if oc_cxxflags.is_a?(String)
      ['-fno-aligned-allocation', '-D_LIBCPP_AVAILABILITY_DISABLE'].each do |cxxf|
        oc_cxxflags << cxxf unless oc_cxxflags.include?(cxxf)
      end
      oc_config.build_settings['OTHER_CPLUSPLUSFLAGS'] = oc_cxxflags

      oc_ldflags = oc_config.build_settings['OTHER_LDFLAGS'] || ['$(inherited)']
      oc_ldflags = [oc_ldflags] if oc_ldflags.is_a?(String)
      [{ld_ruby_list}].each do |flag|
        oc_ldflags << flag unless oc_ldflags.include?(flag)
      end
      oc_config.build_settings['OTHER_LDFLAGS'] = oc_ldflags
    end
  end
# END OLDCOOK IOS12 HOOK
"""
    if "BEGIN OLDCOOK IOS12 HOOK" not in text:
        m = re.search(r"post_install\s+do\s*\|(\w+)\|", text)
        if m:
            var_name = m.group(1)
            adj_hook = hook.replace("installer.", f"{var_name}.")
            text = text[: m.end()] + "\n" + adj_hook + text[m.end() :]
        else:
            text += f"\npost_install do |installer|\n{hook}\nend\n"

    podfile.write_text(text, encoding="utf-8")
    print(f"[ok] Patched {podfile.name} (platform :ios, '{min_ios}', ld_classic + weak overlays + polyfill)")


def format_override_entry(pkg: str, spec: dict) -> list[str]:
    out = [f"  {pkg}:"]
    if "path" in spec:
        out.append(f"    path: {spec['path']}")
    elif "git" in spec:
        out.append("    git:")
        out.append(f"      url: {spec['git']['url']}")
        if "path" in spec["git"]:
            out.append(f"      path: {spec['git']['path']}")
        if "ref" in spec["git"]:
            out.append(f"      ref: {spec['git']['ref']}")
    elif "version" in spec:
        out = [f"  {pkg}: {spec['version']}"]
    return out


def patch_pubspec_overrides(pubspec: Path, recipe_overrides: dict) -> None:
    if not pubspec.exists():
        return
    text = pubspec.read_text(encoding="utf-8")
    text = re.sub(r"\n?[ \t]*# BEGIN OLDCOOK OVERRIDES.*?# END OLDCOOK OVERRIDES\n?", "\n", text, flags=re.S)

    compat_dir = ROOT / "compat-packages"
    auto_overrides: dict[str, dict] = {}
    if compat_dir.exists():
        for child in sorted(compat_dir.iterdir()):
            if (child / "pubspec.yaml").exists() and re.search(rf"^\s*{re.escape(child.name)}\s*:", text, re.M):
                rel = Path("..") / ".." / "compat-packages" / child.name
                auto_overrides[child.name] = {"path": str(rel)}

    merged = {**auto_overrides, **recipe_overrides}
    if not merged:
        return

    m_sec = re.search(r"^dependency_overrides\s*:\s*$", text, re.M)
    if m_sec:
        after_start = m_sec.end()
        m_next = re.search(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", text[after_start:], re.M)
        sec_end = after_start + m_next.start() if m_next else len(text)
        sec_body = text[after_start:sec_end]

        lines = ["  # BEGIN OLDCOOK OVERRIDES"]
        for pkg, spec in merged.items():
            if pkg not in recipe_overrides and re.search(rf"^\s{{2}}{re.escape(pkg)}\s*:", sec_body, re.M):
                continue
            lines.extend(format_override_entry(pkg, spec))
        lines.append("  # END OLDCOOK OVERRIDES")

        if len(lines) > 2:
            block = "\n" + "\n".join(lines) + "\n"
            updated = text[:sec_end].rstrip("\n") + block + ("\n" + text[sec_end:].lstrip("\n") if sec_end < len(text) else "")
            pubspec.write_text(updated, encoding="utf-8")
            print(f"[ok] Injected {len(merged)} package override(s) into dependency_overrides")
    else:
        lines = ["\n# BEGIN OLDCOOK OVERRIDES", "dependency_overrides:"]
        for pkg, spec in merged.items():
            lines.extend(format_override_entry(pkg, spec))
        lines.append("# END OLDCOOK OVERRIDES\n")
        pubspec.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")
        print(f"[ok] Injected {len(merged)} package override(s) into pubspec.yaml")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recipe", help="Recipe name under recipes/<name>")
    ap.add_argument("--ref", help="Override upstream git tag/branch/commit")
    ap.add_argument("--overlay-only", action="store_true", help="Skip git sync; apply overlays onto existing work/<name>")
    ap.add_argument("--full-clone", action="store_true", help="Force full git history clone")
    args = ap.parse_args()

    recipe_dir = ROOT / "recipes" / args.recipe
    recipe_file = recipe_dir / "recipe.json"
    if not recipe_file.exists():
        print(f"[err] Recipe not found: {recipe_file}", file=sys.stderr)
        return 1

    cfg = json.loads(recipe_file.read_text(encoding="utf-8"))
    min_ios = str(cfg.get("min_ios", "12.2"))
    target_ref = args.ref or cfg.get("ref", "main")
    full_hist = args.full_clone or bool(cfg.get("clone_full_history", False))
    work_dir = ROOT / "work" / args.recipe

    if not args.overlay_only:
        sync_upstream(cfg["repo"], target_ref, work_dir, shallow=not full_hist)

    ios_dir = work_dir / cfg.get("ios_subdir", "ios")
    polyfill_rel = str(Path("..") / ".." / ".." / "compat-packages" / "ios12_polyfill")
    weak_fws = cfg.get("weak_frameworks", WEAK_IOS13_FRAMEWORKS)

    patch_pbxproj(ios_dir / "Runner.xcodeproj/project.pbxproj", min_ios)
    patch_plist(ios_dir / "Runner/Info.plist", min_ios, strip_scene=cfg.get("strip_scene_manifest", True))
    patch_plist(ios_dir / "Flutter/AppFrameworkInfo.plist", min_ios, strip_scene=False)
    patch_scene_delegate(ios_dir)
    patch_podfile(ios_dir / "Podfile", min_ios, polyfill_rel, weak_fws)
    patch_pubspec_overrides(work_dir / "pubspec.yaml", cfg.get("dependency_overrides", {}))

    patches_dir = recipe_dir / "patches"
    if patches_dir.exists():
        for patch_file in sorted(patches_dir.glob("*.patch")):
            run(["git", "apply", "--3way", str(patch_file)], cwd=work_dir)
            print(f"[ok] Applied patch {patch_file.name}")

    print(f"[done] Workspace ready at: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
