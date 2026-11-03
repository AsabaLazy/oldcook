#!/usr/bin/env python3
"""Relink gen_snapshot's raw App.framework/App into a standard iOS 12 Mach-O dylib.

Why this is required for iOS 12 (`dyld2`):
1. Flutter 3.47+ `gen_snapshot` emits a minimal Mach-O file without `LC_DYLD_INFO_ONLY` and places
   `LC_SEGMENT_64 (__TEXT)` at load command index 6 instead of 0. While iOS 13+ `dyld3` accepts it,
   iOS 12 `dyld2` rejects it during `dlopen()`.
2. `dart::BSS::Initialize` writes FFI callback metadata into `__DATA,__bss` immediately following
   `__TEXT,__const` (page-aligned). Relinking `__TEXT,__text`, `__TEXT,__const`, and a 16KB-aligned
   writable `.zerofill __DATA,__bss` via `clang -dynamiclib` produces a standard `LC_DYLD_INFO_ONLY`
   dylib with identical VMA offsets (`_kDartSnapshotText` at `0x4000`, `_kDartSnapshotData` after
   `__text`, and writable `__DATA,__bss`).
"""

import argparse
import struct
import subprocess
import tempfile
from pathlib import Path


def clear_linker_signed_flag(macho: bytearray) -> bytes:
    if len(macho) < 32:
        return bytes(macho)
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from("<IIIIIIII", macho, 0)
    if magic != 0xFEEDFACF:
        return bytes(macho)
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", macho, off)
        if cmd == 0x1D:  # LC_CODE_SIGNATURE
            dataoff, _ = struct.unpack_from("<II", macho, off + 8)
            _, _, count = struct.unpack_from(">III", macho, dataoff)
            for i in range(count):
                _, boff = struct.unpack_from(">II", macho, dataoff + 12 + i * 8)
                cd_off = dataoff + boff
                if struct.unpack_from(">I", macho, cd_off)[0] == 0xFADE0C02:
                    flags = struct.unpack_from(">I", macho, cd_off + 12)[0]
                    struct.pack_into(">I", macho, cd_off + 12, flags & ~0x20000)
        off += cmdsize
    return bytes(macho)


def relink_app_binary(app_path: Path, min_ios: str = "12.2", sdk_path: Path | None = None) -> None:
    raw = app_path.read_bytes()
    if struct.unpack_from(">I", raw, 0)[0] == 0xCAFEBABE:
        _, _, slice_off, slice_sz, _ = struct.unpack_from(">IIIII", raw, 8)
        app_slice = raw[slice_off : slice_off + slice_sz]
    else:
        app_slice = raw

    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from("<IIIIIIII", app_slice, 0)
    if magic != 0xFEEDFACF:
        raise ValueError(f"Unsupported Mach-O magic {hex(magic)} in {app_path}")

    off = 32
    text_bytes = b""
    const_bytes = b""
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", app_slice, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            nsects = struct.unpack_from("<I", app_slice, off + 64)[0]
            soff = off + 72
            for _ in range(nsects):
                sname = app_slice[soff : soff + 16].rstrip(b"\x00").decode("utf-8", errors="ignore")
                sz = struct.unpack_from("<Q", app_slice, soff + 40)[0]
                foff = struct.unpack_from("<I", app_slice, soff + 48)[0]
                if sname == "__text":
                    text_bytes = app_slice[foff : foff + sz]
                elif sname == "__const":
                    const_bytes = app_slice[foff : foff + sz]
                soff += 80
        off += cmdsize

    if not text_bytes or not const_bytes:
        raise RuntimeError(f"Failed to extract __text / __const from {app_path}")

    with tempfile.TemporaryDirectory(prefix="oc_relink_app_") as td:
        td_p = Path(td)
        (td_p / "text.bin").write_bytes(text_bytes)
        (td_p / "const.bin").write_bytes(const_bytes)
        (td_p / "app.s").write_text(
            ".section __TEXT,__text,regular,pure_instructions\n"
            ".p2align 14\n"
            ".globl _kDartSnapshotText\n"
            "_kDartSnapshotText:\n"
            f'.incbin "{td_p}/text.bin"\n\n'
            ".section __TEXT,__const\n"
            ".p2align 14\n"
            ".globl _kDartSnapshotData\n"
            "_kDartSnapshotData:\n"
            f'.incbin "{td_p}/const.bin"\n\n'
            ".zerofill __DATA,__bss,__dart_bss,16384,14\n",
            encoding="utf-8",
        )
        out_bin = td_p / "App"
        import sys
        cmd = ["clang", "-target", f"arm64-apple-ios{min_ios}", "-dynamiclib"]
        if sdk_path and sdk_path.exists():
            cmd += ["-isysroot", str(sdk_path)]
        if sys.platform == "darwin":
            cmd += ["-Wl,-ld_classic"]
        else:
            cmd += ["-fuse-ld=lld", "-Wl,-adhoc_codesign"]
        cmd += [
            "-install_name", "@rpath/App.framework/App",
            "-current_version", "1.0.0",
            "-compatibility_version", "1.0.0",
            str(td_p / "app.s"),
            "-o", str(out_bin),
        ]
        subprocess.run(cmd, check=True)
        final_bytes = clear_linker_signed_flag(bytearray(out_bin.read_bytes()))
        app_path.write_bytes(final_bytes)
    print(f"[ok] Relinked {app_path} with LC_DYLD_INFO_ONLY + writable __DATA,__bss (min_ios={min_ios})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("app_binary", type=Path, help="Path to App.framework/App")
    ap.add_argument("--min-ios", default="12.2", help="Target iOS deployment floor")
    ap.add_argument("--sdk", type=Path, help="Optional explicit iPhoneOS SDK path")
    args = ap.parse_args()
    relink_app_binary(args.app_binary, args.min_ios, args.sdk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
