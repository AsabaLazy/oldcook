# oldcook

无需回退上游提交、以 Linux 为优先的现代 Flutter 与原生开源 iOS 应用 iOS 12 向后移植工厂。

[English](README.md) | 简体中文

## 安装

1. 在 Linux 或 macOS 上克隆本仓库，或在 GitHub Actions 中直接引用 `AsabaLazy/oldcook@main`。
2. 运行 `./tools/fetch_sdk.sh` 与 `python3 tools/selftest.py` 下载 `iPhoneOS12.4.sdk` 并校验本地工具链。
3. 运行 `python3 tools/apply_recipe.py <recipe>` 生成上游补丁工作区，或运行 `python3 tools/audit_ipa.py <path/to/App.ipa>` 对安装包执行离线符号体检。

## 简介

oldcook 是一套解耦的构建与补丁工具链，可将现代 Flutter 3.47+ 及原生 iOS 项目的最低系统要求降至 iOS 12.2–12.5.7。它涵盖 `flutter_tools` 版本限制解锁、`Flutter.framework` 引擎补丁、`App.framework` 针对 iOS 12 `dyld2` 的 Mach-O 重链接、Objective-C `+load` 运行时垫片（`Metal`、`UIScene`、`UITraitCollection`、`UIKit`）以及 CocoaPods 插件源码兼容层。

所有补丁均在构建期动态注入，不污染上游仓库与全局 `~/.pub-cache`（插件副本隔离在 `work/<recipe>/.oldcook_plugins/`），且每次打包均通过 `iPhoneOS12.4.sdk` 离线符号守门校验。架构细节与符号体检规则见 [Agent.md](Agent.md)。

## 更新日志

见 [Releases](https://github.com/AsabaLazy/oldcook/releases) 页面。

## 问题反馈

构建报错、缺失的 iOS 12 符号或新应用适配请求请在 [Issues](https://github.com/AsabaLazy/oldcook/issues) 中提交。

## 常见问题

见 [Agent.md](Agent.md)。
