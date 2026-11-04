# oldcook

面向 Flutter 3.47+ 与原生 iOS 项目的 iOS 12.2–12.5.7 兼容构建与补丁工具链。本项目使用 AI 辅助编码开发。

[English](README.md) | 简体中文

## 安装

1. 在 Linux 或 macOS 上克隆本仓库，或在 GitHub Actions 中引用 `AsabaLazy/oldcook@main`。
2. 运行 `./tools/fetch_sdk.sh` 与 `python3 tools/selftest.py` 下载 iOS 12.4 SDK 并执行本地自检。
3. 运行 `python3 tools/apply_recipe.py <recipe>` 生成上游补丁工作区，或运行 `python3 tools/audit_ipa.py <path/to/App.ipa>` 检查 Mach-O 头部与符号引用。

## 简介

oldcook 提供脚本与运行时垫片，用于将 Flutter 3.47+ 应用的最低部署目标降至 iOS 12.2–12.5.7。它包含 flutter_tools 版本限制补丁、Flutter.framework 引擎补丁、App.framework 针对 iOS 12 dyld2 的 Mach-O 重链接、Objective-C 运行时垫片（Metal、UIScene、UITraitCollection、UIKit）以及 CocoaPods 插件源码修改。

补丁在独立工作区中于构建期应用，生成的安装包通过 iOS 12.4 SDK 符号表进行离线静态检查。本项目使用 AI 辅助编码开发。技术细节见 [Agent.md](Agent.md)。

## 更新日志

见 [Releases](https://github.com/AsabaLazy/oldcook/releases) 页面。

## 问题反馈

构建报错、缺失的 iOS 12 符号或兼容性问题请在 [Issues](https://github.com/AsabaLazy/oldcook/issues) 中提交。
