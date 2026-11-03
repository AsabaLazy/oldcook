#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_DIR="${ROOT_DIR}/sdks"
RELEASE_BASE="https://github.com/theos/sdks/releases/download/master-146e41f"

mkdir -p "${SDK_DIR}"

fetch_one() {
  local sdk_name="$1"
  if [[ -d "${SDK_DIR}/${sdk_name}.sdk" ]]; then
    echo "[ok] ${sdk_name}.sdk already exists in ${SDK_DIR}"
    return 0
  fi
  local archive="${SDK_DIR}/${sdk_name}.sdk.tar.xz"
  echo "[fetch] Downloading ${sdk_name}.sdk.tar.xz ..."
  curl -fL --retry 3 -o "${archive}" "${RELEASE_BASE}/${sdk_name}.sdk.tar.xz"
  echo "[extract] Unpacking ${sdk_name}.sdk ..."
  tar -xJf "${archive}" -C "${SDK_DIR}"
  rm -f "${archive}"
  echo "[ok] Installed ${SDK_DIR}/${sdk_name}.sdk"
}

# iPhoneOS12.4.sdk: ground-truth iOS 12 symbol table (.tbd) for offline auditing
fetch_one "iPhoneOS12.4"

if [[ "${1:-}" == "--with-compile-sdk" ]]; then
  # iPhoneOS14.5.sdk: newer headers for compiling modern sources with -miphoneos-version-min=12.0
  fetch_one "iPhoneOS14.5"
fi
