#!/usr/bin/env python3
"""Offline Linux Mach-O / .ipa iOS 12 compatibility auditor.

Checks every Mach-O binary inside an .ipa, .app, or directory against iPhoneOS12.4.sdk (.tbd):
1. Info.plist MinimumOSVersion & UIApplicationSceneManifest
2. Mach-O deployment target (LC_VERSION_MIN_IPHONEOS / LC_BUILD_VERSION > 12.0)
3. Fatal dyld load commands unsupported on iOS 12 (LC_DYLD_CHAINED_FIXUPS 0x80000034, LC_DYLD_EXPORTS_TRIE 0x80000033)
4. Missing strongly-linked system frameworks/dylibs (e.g. libswift_Concurrency.dylib, UniformTypeIdentifiers)
5. Undefined external symbols missing from iOS 12.4 SDK (split into STRONG launch-crashers vs WEAK runtime-guarded)
"""

import argparse
import json
import plistlib
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SDK = ROOT / "sdks" / "iPhoneOS12.4.sdk"

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA
CPU_TYPE_ARM64 = 0x0100000C

LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LAZY_LOAD_DYLIB = 0x20
LC_VERSION_MIN_IPHONEOS = 0x25
LC_BUILD_VERSION = 0x32
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_DYLD_CHAINED_FIXUPS = 0x80000034

# Swift 5.0 ABI-stable runtime dylibs present in /usr/lib/swift/ on iOS 12.2 - 12.5.7
# (Omitted from theos iPhoneOS12.4.sdk because Xcode 10.3 stored them under XcodeDefault.xctoolchain)
IOS12_2_SWIFT_DYLIBS = {
    f"/usr/lib/swift/libswift{name}.dylib"
    for name in (
        "AVFoundation", "Contacts", "Core", "CoreAudio", "CoreData",
        "CoreFoundation", "CoreGraphics", "CoreImage", "CoreLocation",
        "CoreMedia", "Darwin", "Dispatch", "Foundation", "GLKit", "MapKit",
        "Metal", "MetalKit", "ModelIO", "NaturalLanguage", "ObjectiveC",
        "Photos", "QuartzCore", "SceneKit", "SpriteKit", "UIKit", "os", "simd",
    )
}

# Symbols automatically emitted by Clang ONLY when -miphoneos-version-min >= 13.0 / 14.0
COMPILER_MINOS13_ARTIFACTS = {
    "_objc_opt_class",
    "_objc_opt_isKindOfClass",
    "_objc_opt_new",
    "_objc_opt_respondsToSelector",
    "_objc_opt_self",
    "_OBJC_CLASS_$_NSConstantIntegerNumber",
    "_OBJC_CLASS_$_NSConstantDoubleNumber",
    "_OBJC_CLASS_$_NSConstantFloatNumber",
    "_OBJC_CLASS_$_NSConstantArray",
    "_OBJC_CLASS_$_NSConstantDictionary",
    "___NSDictionary0__struct",
    "___NSArray0__struct",
}

IGNORED_SYMBOLS = {
    "___chkstk_darwin",
    "__mh_execute_header",
    "__mh_dylib_header",
    "__mh_bundle_header",
    "dyld_stub_binder",
}


def fmt_ver(raw: int) -> str:
    return f"{(raw >> 16) & 0xFFFF}.{(raw >> 8) & 0xFF}.{raw & 0xFF}"


def ver_tuple(ver_str: str) -> tuple[int, ...]:
    return tuple(int(x) for x in ver_str.split(".") if x.isdigit())


def load_ios12_sdk_index(sdk_dir: Path) -> tuple[set[str], set[str]]:
    cache_file = sdk_dir.parent / f".{sdk_dir.name}_index.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return set(data["symbols"]), set(data["install_names"])

    if not sdk_dir.exists():
        raise FileNotFoundError(
            f"SDK not found at {sdk_dir}. Run: ./tools/fetch_sdk.sh"
        )

    symbols: set[str] = set()
    install_names: set[str] = set()

    list_key_re = re.compile(
        r"^\s*(symbols|weak-def-symbols|objc-classes|objc-eh-types|objc-ivars)\s*:\s*\[(.*)",
    )
    iname_re = re.compile(r"^\s*install-name\s*:\s*['\"]?([^'\"\s#]+)['\"]?")

    for tbd in sdk_dir.rglob("*.tbd"):
        text = tbd.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            m_in = iname_re.match(line)
            if m_in:
                install_names.add(m_in.group(1))
                i += 1
                continue

            m_key = list_key_re.match(line)
            if m_key:
                kind = m_key.group(1)
                buf = [m_key.group(2)]
                while "]" not in buf[-1] and i + 1 < len(lines):
                    i += 1
                    buf.append(lines[i])
                joined = " ".join(buf).split("]", 1)[0]
                for raw_tok in joined.split(","):
                    tok = raw_tok.strip().strip("'\"")
                    if not tok:
                        continue
                    if kind in ("symbols", "weak-def-symbols"):
                        symbols.add(tok)
                    elif kind == "objc-classes":
                        cls = tok.lstrip("_")
                        symbols.add(f"_OBJC_CLASS_$_{cls}")
                        symbols.add(f"_OBJC_METACLASS_$_{cls}")
                        symbols.add(f"_{cls}")
                    elif kind == "objc-eh-types":
                        cls = tok.lstrip("_")
                        symbols.add(f"_OBJC_EHTYPE_$_{cls}")
                    elif kind == "objc-ivars":
                        ivar = tok.lstrip("_")
                        symbols.add(f"_OBJC_IVAR_$_{ivar}")
            i += 1

    cache_file.write_text(
        json.dumps({"symbols": sorted(symbols), "install_names": sorted(install_names)}),
        encoding="utf-8",
    )
    return symbols, install_names


def parse_macho_file(path: Path) -> dict | None:
    try:
        with path.open("rb") as f:
            head = f.read(32)
            if len(head) < 28:
                return None
            magic = struct.unpack("<I", head[:4])[0]
            offset = 0
            if magic in (FAT_MAGIC, FAT_CIGAM):
                _, nfat = struct.unpack(">II", head[:8])
                f.seek(8)
                chosen = None
                for _ in range(nfat):
                    cputype, cpusubtype, off, size, align = struct.unpack(">iiIII", f.read(20))
                    if cputype == CPU_TYPE_ARM64:
                        # Prefer standard arm64 (cpusubtype 0) over arm64e if multiple slices exist
                        if chosen is None or (cpusubtype & 0xFF) == 0:
                            chosen = off
                if chosen is None:
                    return None
                offset = chosen
                f.seek(offset)
                head = f.read(32)
                if len(head) < 32:
                    return None
                magic = struct.unpack("<I", head[:4])[0]

            if magic != MH_MAGIC_64:
                return None

            _, cputype, _, filetype, ncmds, sizeofcmds, _ = struct.unpack("<7I", head[:28])
            if cputype != CPU_TYPE_ARM64:
                return None
            cmds_blob = f.read(sizeofcmds)
    except OSError:
        return None

    minos = None
    sdk = None
    fatal_lcs: list[str] = []
    dylibs: list[tuple[str, bool]] = []

    pos = 0
    for _ in range(ncmds):
        if pos + 8 > len(cmds_blob):
            break
        cmd, cmdsize = struct.unpack_from("<II", cmds_blob, pos)
        if cmdsize < 8 or pos + cmdsize > len(cmds_blob):
            break

        if cmd == LC_VERSION_MIN_IPHONEOS and cmdsize >= 16:
            v_min, v_sdk = struct.unpack_from("<II", cmds_blob, pos + 8)
            minos, sdk = fmt_ver(v_min), fmt_ver(v_sdk)
        elif cmd == LC_BUILD_VERSION and cmdsize >= 24:
            _, v_min, v_sdk, _ = struct.unpack_from("<IIII", cmds_blob, pos + 8)
            minos, sdk = fmt_ver(v_min), fmt_ver(v_sdk)
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            fatal_lcs.append("LC_DYLD_CHAINED_FIXUPS(0x80000034)")
        elif cmd == LC_DYLD_EXPORTS_TRIE:
            fatal_lcs.append("LC_DYLD_EXPORTS_TRIE(0x80000033)")
        elif cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB) and cmdsize >= 24:
            str_off = struct.unpack_from("<I", cmds_blob, pos + 8)[0]
            if pos + str_off < pos + cmdsize:
                raw = cmds_blob[pos + str_off : pos + cmdsize].split(b"\x00", 1)[0]
                is_weak = cmd == LC_LOAD_WEAK_DYLIB
                dylibs.append((raw.decode("utf-8", errors="replace"), is_weak))

        pos += cmdsize

    return {
        "minos": minos,
        "sdk": sdk,
        "fatal_lcs": fatal_lcs,
        "dylibs": dylibs,
    }


def nm_defined_symbols(binary: Path) -> set[str]:
    syms: set[str] = set()
    for cmd in (
        ["llvm-nm", "--arch=arm64", "-g", "--defined-only", "-j", str(binary)],
        ["llvm-nm", "-g", "--defined-only", "-j", str(binary)],
    ):
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout:
            syms.update(line.strip() for line in res.stdout.splitlines() if line.strip())
            break

    # Also read Mach-O exports trie (covers stripped Release frameworks using LC_DYLD_EXPORTS_TRIE)
    trie = subprocess.run(
        ["llvm-objdump", "--macho", "--exports-trie", str(binary)],
        capture_output=True,
        text=True,
        check=False,
    )
    if trie.returncode == 0:
        for line in trie.stdout.splitlines():
            parts = line.strip().split()
            # Format: "0x12345678  _SymbolName" or "[re-export] _SymbolName (from ...)"
            for tok in parts:
                if tok.startswith("_"):
                    syms.add(tok)
                    break
    return syms


def nm_undefined_darwin(binary: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (strong_undefs, weak_undefs) mapping symbol -> source library hint."""
    res = subprocess.run(
        ["llvm-nm", "--arch=arm64", "-u", "-m", str(binary)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        res = subprocess.run(
            ["llvm-nm", "-u", "-m", str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
    strong: dict[str, str] = {}
    weak: dict[str, str] = {}
    line_re = re.compile(
        r"\(undefined\)(.*?)external\s+(\S+)(?:\s+\(from\s+([^)]+)\))?"
    )
    for line in res.stdout.splitlines():
        m = line_re.search(line)
        if not m:
            continue
        qualifiers = m.group(1) or ""
        is_weak = "weak" in qualifiers.split()
        sym = m.group(2)
        src = m.group(3) or "unknown"
        if is_weak:
            weak[sym] = src
        else:
            strong[sym] = src
    return strong, weak


def audit_bundle(root_dir: Path, sdk_symbols: set[str], sdk_inames: set[str], target_ver: str) -> dict:
    target_t = ver_tuple(target_ver)
    app_dirs = list(root_dir.rglob("*.app"))
    scan_base = app_dirs[0] if app_dirs else root_dir

    plist_info = {}
    info_plist = scan_base / "Info.plist"
    if info_plist.exists():
        with info_plist.open("rb") as f:
            pl = plistlib.load(f)
        plist_info = {
            "CFBundleIdentifier": pl.get("CFBundleIdentifier"),
            "CFBundleShortVersionString": pl.get("CFBundleShortVersionString"),
            "MinimumOSVersion": pl.get("MinimumOSVersion"),
            "has_UIApplicationSceneManifest": "UIApplicationSceneManifest" in pl,
        }

    binaries: list[tuple[Path, dict]] = []
    for p in sorted(scan_base.rglob("*")):
        if p.is_file() and not p.is_symlink() and p.suffix not in (".plist", ".png", ".nib", ".car", ".ttf", ".otf", ".json", ".metallib", ".txt"):
            meta = parse_macho_file(p)
            if meta:
                binaries.append((p, meta))

    bundled_exports: set[str] = set()
    bundled_names: set[str] = set()
    for p, _ in binaries:
        bundled_exports |= nm_defined_symbols(p)
        bundled_names.add(p.name)
        bundled_names.add(p.stem)

    results = []
    for p, meta in binaries:
        rel = str(p.relative_to(scan_base))
        minos = meta["minos"]
        minos_too_high = bool(minos and ver_tuple(minos) > target_t)

        missing_strong_dylibs = []
        missing_weak_dylibs = []
        for dylib, is_weak in meta["dylibs"]:
            if dylib.startswith(("@rpath/", "@executable_path/", "@loader_path/")):
                base_name = Path(dylib).name
                if base_name not in bundled_names and dylib not in sdk_inames:
                    sys_swift = f"/usr/lib/swift/{base_name}"
                    if sys_swift not in sdk_inames and sys_swift not in IOS12_2_SWIFT_DYLIBS:
                        (missing_weak_dylibs if is_weak else missing_strong_dylibs).append(dylib)
            elif dylib not in sdk_inames and dylib not in IOS12_2_SWIFT_DYLIBS:
                (missing_weak_dylibs if is_weak else missing_strong_dylibs).append(dylib)

        strong_u, weak_u = nm_undefined_darwin(p)
        missing_strong_syms = {}
        missing_weak_syms = {}

        for sym, src in strong_u.items():
            if sym in IGNORED_SYMBOLS or sym in bundled_exports or src in bundled_names:
                continue
            if sym not in sdk_symbols:
                missing_strong_syms[sym] = src

        for sym, src in weak_u.items():
            if sym in IGNORED_SYMBOLS or sym in bundled_exports or src in bundled_names:
                continue
            if sym not in sdk_symbols:
                missing_weak_syms[sym] = src

        results.append({
            "binary": rel,
            "minos": minos,
            "sdk": meta["sdk"],
            "minos_exceeds_target": minos_too_high,
            "fatal_load_commands": meta["fatal_lcs"],
            "missing_strong_dylibs": missing_strong_dylibs,
            "missing_weak_dylibs": missing_weak_dylibs,
            "missing_strong_symbols": missing_strong_syms,
            "missing_weak_symbols": missing_weak_syms,
        })

    return {
        "target_ios": target_ver,
        "bundle": scan_base.name,
        "info_plist": plist_info,
        "binary_count": len(results),
        "binaries": results,
    }


def print_report(rep: dict) -> int:
    print(f"Bundle: {rep['bundle']}  (Target iOS <= {rep['target_ios']}, Mach-O arm64 binaries: {rep['binary_count']})")
    pl = rep["info_plist"]
    if pl:
        print(
            f"Info.plist: id={pl.get('CFBundleIdentifier')}  minOS={pl.get('MinimumOSVersion')}  "
            f"hasSceneManifest={pl.get('has_UIApplicationSceneManifest')}"
        )

    blockers = 0
    minos_high_list = []
    chained_list = []
    all_strong_dylibs: dict[str, list[str]] = {}
    c_objc_strong_syms: dict[str, set[str]] = {}
    compiler_artifact_syms: dict[str, set[str]] = {}
    swift_strong_syms: dict[str, set[str]] = {}
    all_weak_syms: dict[str, set[str]] = {}

    ios12_swift_short = {Path(p).stem for p in IOS12_2_SWIFT_DYLIBS}

    for b in rep["binaries"]:
        name = b["binary"]
        if b["minos_exceeds_target"]:
            minos_high_list.append(f"{name} (minos={b['minos']})")
            blockers += 1
        if b["fatal_load_commands"]:
            chained_list.append(f"{name}: {', '.join(b['fatal_load_commands'])}")
            blockers += 1
        for d in b["missing_strong_dylibs"]:
            all_strong_dylibs.setdefault(d, []).append(name)
            blockers += 1
        for sym, src in b["missing_strong_symbols"].items():
            key = f"{sym} [{src}]"
            if sym in COMPILER_MINOS13_ARTIFACTS:
                compiler_artifact_syms.setdefault(key, set()).add(name)
                blockers += 1
            elif sym.startswith("_$s") or src.startswith("libswift"):
                # Only flag Swift symbols from non-iOS12.2 Swift overlays or newer Foundation/Network Swift APIs
                if src not in ios12_swift_short:
                    swift_strong_syms.setdefault(key, set()).add(name)
                    blockers += 1
            else:
                c_objc_strong_syms.setdefault(key, set()).add(name)
                blockers += 1
        for sym, src in b["missing_weak_symbols"].items():
            if not sym.startswith("_$s") and not src.startswith("libswift"):
                all_weak_syms.setdefault(f"{sym} [{src}]", set()).add(name)

    print(f"\n[1] Mach-O minos > {rep['target_ios']}: {len(minos_high_list)} binary(ies)")
    for item in minos_high_list[:15]:
        print(f"    - {item}")
    if len(minos_high_list) > 15:
        print(f"    ... and {len(minos_high_list) - 15} more")

    print(f"\n[2] Fatal iOS 12 dyld load commands (Chained Fixups / Exports Trie): {len(chained_list)} binary(ies)")
    for item in chained_list[:12]:
        print(f"    - {item}")

    print(f"\n[3] Missing STRONG dylibs/frameworks on iOS 12.2+: {len(all_strong_dylibs)}")
    for dylib, owners in sorted(all_strong_dylibs.items()):
        print(f"    - {dylib}  <- {', '.join(owners[:4])}{'...' if len(owners) > 4 else ''}")

    print(f"\n[4] Missing STRONG C/ObjC symbols on iOS 12 (real API gaps): {len(c_objc_strong_syms)}")
    for sym, owners in sorted(c_objc_strong_syms.items())[:45]:
        print(f"    - {sym}  <- {', '.join(sorted(owners)[:3])}")
    if len(c_objc_strong_syms) > 45:
        print(f"    ... and {len(c_objc_strong_syms) - 45} more")

    print(f"\n[5] Missing iOS 13+ Swift overlay symbols: {len(swift_strong_syms)}  |  Clang minos>=13 auto-optimizations: {len(compiler_artifact_syms)}")
    for sym, owners in sorted(swift_strong_syms.items())[:15]:
        print(f"    - {sym}  <- {', '.join(sorted(owners)[:3])}")
    if len(swift_strong_syms) > 15:
        print(f"    ... and {len(swift_strong_syms) - 15} more Swift overlay symbols")

    print(f"\n[6] Missing WEAK C/ObjC symbols (@available guarded / runtime polyfill candidates): {len(all_weak_syms)}")
    for sym, owners in sorted(all_weak_syms.items())[:15]:
        print(f"    - {sym}  <- {', '.join(sorted(owners)[:3])}")
    if len(all_weak_syms) > 15:
        print(f"    ... and {len(all_weak_syms) - 15} more")

    status = "PASS (iOS 12 launch-safe)" if blockers == 0 else f"BLOCKED ({blockers} launch-blocking issue(s) found)"
    print(f"\nVerdict: {status}")
    return 0 if blockers == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="Path to .ipa, .app bundle, or directory containing Mach-O binaries")
    ap.add_argument("--sdk", type=Path, default=DEFAULT_SDK, help="Path to iPhoneOS12.4.sdk")
    ap.add_argument("--target", default="12.4", help="Target iOS version ceiling (default: 12.4)")
    ap.add_argument("--json", type=Path, help="Write full structured audit report to JSON file")
    args = ap.parse_args()

    sdk_symbols, sdk_inames = load_ios12_sdk_index(args.sdk)
    target_path = Path(args.input)
    if not target_path.exists():
        print(f"[err] Input not found: {target_path}", file=sys.stderr)
        return 1

    if target_path.is_file() and target_path.suffix.lower() == ".ipa":
        with tempfile.TemporaryDirectory(prefix="oldcook_ipa_") as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(target_path, "r") as zf:
                zf.extractall(tmp_path)
            # Restore symlink / executable handling irrelevant for static read
            report = audit_bundle(tmp_path, sdk_symbols, sdk_inames, args.target)
    else:
        report = audit_bundle(target_path, sdk_symbols, sdk_inames, args.target)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] Wrote full JSON report to {args.json}\n")

    return print_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
