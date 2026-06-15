# Private SDK Runtime Package Template

This directory documents the intended private package layout for official Sqray
SDK runtime binaries. It is a template only. Do not commit SDK binaries here.

Expected package root:

```text
opensqray_sdk_runtime/
  linux-x86_64/lib/
  linux-arm64/lib/
  macos-arm64/lib/
  macos-x86_64/lib/
  windows-x86_64/bin/
  windows-x86_64/lib/      # optional fallback
```

The service library names are:

- Linux: `libsqrayslideservice.so`
- macOS: `libsqrayslideservice.dylib`
- Windows: `sqrayslideservice.dll`

Before building or publishing an internal runtime wheel, run:

```bash
python3 tools/check_sdk_runtime_package.py /path/to/opensqray_sdk_runtime \
  --platform-tag linux-x86_64
```

After installing the wheel, run the practical validator against a real SDPC
slide:

```bash
python3 tools/validate_sdk_runtime.py data/20220514_145829_0.sdpc \
  --workers 4 \
  --patch-size 256 \
  --patch-count 16
```

The static checker is not sufficient by itself. A runtime package is usable only
after the real SDK validator passes on the target platform.
