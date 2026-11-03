#!/usr/bin/env bash
set -euo pipefail

# Sign and optionally USB-install an unsigned .ipa on Linux (supports jailbroken ldid or stock zsign)
# Usage:
#   Jailbroken (AppSync): ./tools/sign_and_install.sh input.ipa --adhoc [--install]
#   Stock iOS 12:         ./tools/sign_and_install.sh input.ipa --p12 cert.p12 --pass "123" --profile app.mobileprovision [--install]

IPA_IN="${1:?Usage: $0 <input.ipa> [--adhoc | --p12 <file> --pass <pw> --profile <mobileprovision>] [--install]}"
shift

MODE=""
P12=""
PASS=""
PROFILE=""
DO_INSTALL=0
IPA_OUT="${IPA_IN%.ipa}-signed.ipa"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adhoc) MODE="adhoc"; shift ;;
    --p12) MODE="cert"; P12="$2"; shift 2 ;;
    --pass) PASS="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --out) IPA_OUT="$2"; shift 2 ;;
    --install) DO_INSTALL=1; shift ;;
    *) echo "[err] Unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ "${MODE}" == "cert" ]]; then
  command -v zsign >/dev/null 2>&1 || { echo "[err] zsign not installed (aur/zsign-git or https://github.com/zhlynn/zsign)" >&2; exit 1; }
  zsign -k "${P12}" -p "${PASS}" -m "${PROFILE}" -o "${IPA_OUT}" "${IPA_IN}"
elif [[ "${MODE}" == "adhoc" ]]; then
  if command -v zsign >/dev/null 2>&1; then
    zsign -a -o "${IPA_OUT}" "${IPA_IN}"
  elif command -v ldid >/dev/null 2>&1; then
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "${TMP_DIR}"' EXIT
    unzip -q "${IPA_IN}" -d "${TMP_DIR}"
    find "${TMP_DIR}/Payload" -type f \( -perm -u+x -o -name "*.dylib" \) -exec ldid -S {} + 2>/dev/null || true
    (cd "${TMP_DIR}" && zip -qr "${OLDPWD}/${IPA_OUT}" Payload)
  else
    echo "[err] Install zsign or ldid for ad-hoc signing" >&2
    exit 1
  fi
else
  echo "[err] Specify --adhoc or --p12/--profile" >&2
  exit 1
fi

echo "[ok] Signed IPA: ${IPA_OUT}"

if [[ "${DO_INSTALL}" -eq 1 ]]; then
  command -v ideviceinstaller >/dev/null 2>&1 || { echo "[err] ideviceinstaller not installed" >&2; exit 1; }
  ideviceinstaller -i "${IPA_OUT}"
fi
