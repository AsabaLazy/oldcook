# Engine Patches

- `patch_flutter_ios12.py`: Primary version-resilient semantic patcher for Flutter 3.47+ (`--mode tools-only` for `flutter_tools` + `podhelper.rb` + `native_assets.dart`; `--mode full` for `engine/src/` C++/ObjC++/Swift iOS 12.2 embedder build).
- Optional `<flutter_version>/*.patch`: Any version-specific git patches placed in `engine-patches/<flutter_version>/` are automatically applied after `patch_flutter_ios12.py` by `.github/workflows/build-engine-ios12.yml`.
