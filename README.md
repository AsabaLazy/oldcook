# oldcook

Build and patching toolkit for targeting iOS 12.2–12.5.7 with Flutter 3.47+ and native iOS projects. Built with AI-assisted coding.

English | [简体中文](README.zh-CN.md)

## Install

1. Clone this repository on Linux or macOS, or reference `AsabaLazy/oldcook@main` in GitHub Actions.
2. Run `./tools/fetch_sdk.sh` and `python3 tools/selftest.py` to download the iOS 12.4 SDK and run local verification tests.
3. Run `python3 tools/apply_recipe.py <recipe>` to apply build overlays to an upstream checkout, or run `python3 tools/audit_ipa.py <path/to/App.ipa>` to check Mach-O headers and symbol imports.

## Description

oldcook provides scripts and runtime shims to lower the iOS deployment target of Flutter 3.47+ apps to iOS 12.2–12.5.7. It includes flutter_tools minimum version patches, Flutter.framework engine patches, App.framework Mach-O relinking for iOS 12 dyld2, Objective-C runtime polyfills (Metal, UIScene, UITraitCollection, UIKit), and CocoaPods plugin source modifications.

Patches are applied in an isolated workspace during build time, and built packages are checked offline against the iOS 12.4 SDK symbol tables. This project is developed with AI-assisted coding. See [Agent.md](Agent.md) for technical documentation.

## Changelog

See the [Releases](https://github.com/AsabaLazy/oldcook/releases) page.

## Issues

Report build errors, missing iOS 12 symbols, and compatibility issues in [Issues](https://github.com/AsabaLazy/oldcook/issues).
