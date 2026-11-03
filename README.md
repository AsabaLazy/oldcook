# oldcook

Linux-first overlay factory for backporting modern Flutter and native open-source iOS apps to iOS 12 without rolling back upstream commits.

English | [简体中文](README.zh-CN.md)

## Install

1. Clone this repository on Linux or macOS, or reference `AsabaLazy/oldcook@main` directly in GitHub Actions.
2. Run `./tools/fetch_sdk.sh` and `python3 tools/selftest.py` to set up `iPhoneOS12.4.sdk` and verify the local toolchain.
3. Run `python3 tools/apply_recipe.py <recipe>` to prepare an upstream workspace, or run `python3 tools/audit_ipa.py <path/to/App.ipa>` to audit a built package.

## Description

oldcook is a decoupled build and patching toolkit that lowers the deployment floor of Flutter 3.47+ and native iOS projects to iOS 12.2–12.5.7. It covers `flutter_tools` minimum version unlocks, `Flutter.framework` engine patches, `App.framework` Mach-O `dyld2` relinking, Objective-C `+load` runtime polyfills (`Metal`, `UIScene`, `UITraitCollection`, `UIKit`), and CocoaPods plugin source shims.

Upstream repositories stay untouched. Plugin overrides are isolated under `work/<recipe>/.oldcook_plugins/` rather than modifying `~/.pub-cache`, and every build is gated offline against `iPhoneOS12.4.sdk` before release. See [Agent.md](Agent.md) for architecture details and symbol audit rules.

## Changelog

See the [Releases](https://github.com/AsabaLazy/oldcook/releases) page.

## Issues

Report build failures, missing iOS 12 symbols, and recipe requests in [Issues](https://github.com/AsabaLazy/oldcook/issues).

## FAQ

See [Agent.md](Agent.md).
