# SDK Runtime and Packaging Strategy

This document defines how OpenSqray uses the official Sqray SDK while keeping
the public package minimal, self-consistent, and redistributable without
proprietary binaries.

## Current Decision

OpenSqray has two SDPC paths:

- Native parser: public-safe metadata, associated-image candidates, and format
  research. It does not provide production `read_region()`.
- SDK-backed compatibility: production SDPC pixel reads through
  `OpenSqraySlide`, using a locally configured legal Sqray SDK runtime.

The SDK-backed path is the current practical equivalent of using OpenSlide on
SVS files. Native pixel reading should not be presented as production-ready
until the formal SDPC tile directory and validation rules are proven across
samples.

## Minimal SDK Surface

The public wrapper intentionally exposes only the SDK calls needed for
OpenSlide-like SDPC workflows:

| Need | SDK capability |
| --- | --- |
| open / close slide | `sqrayslide_open`, `sqrayslide_close` |
| SDK-owned buffer release | `sqrayslide_free_memory` |
| geometry | `sqrayslide_get_level_count`, `sqrayslide_get_level_size`, `sqrayslide_get_level_tile_count`, `sqrayslide_get_tile_size` |
| physical metadata | `sqrayslide_get_mpp`, `sqrayslide_get_magnification`, `sqrayslide_get_barcode` |
| associated images | `sqrayslide_read_label_jpeg` for label, thumbnail, macro |
| pixel reads | `sqrayslide_read_region_bgra`, `sqrayslide_read_tile_jpeg` |
| diagnostics | `sqrayslide_get_level_downsample`, `sqrayslide_get_best_level_for_downsample` |

The wrapper does not yet expose SDK color correction, fluorescence channels,
planes, or BGRA-to-JPEG helpers as public OpenSlide-compatible features. Those
APIs are valuable, but they are not part of the minimal SVS/OpenSlide workflow
and need separate semantics before becoming public API.

## OpenSlide Compatibility Boundary

`OpenSqraySlide` is the stable compatibility class. It currently supports:

- `dimensions`
- `level_count`
- `level_dimensions`
- `level_downsamples`
- `properties`
- `associated_images`
- `read_region(location, level, size)`
- `get_thumbnail(size)`
- `get_best_level_for_downsample(downsample)`
- `read_tile_jpeg_bytes(level=..., tile_x=..., tile_y=...)`
- `read_regions(requests, workers=...)` as an OpenSqray high-throughput
  extension
- context-manager and `close()` lifecycle

OpenSlide-style `level_downsamples` are computed from level dimensions because
the observed SDK downsample values can use inverse semantics on real samples.
Raw SDK scale values remain diagnostic properties under
`opensqray.sdk.level_downsample.<level>`.

Out of scope for the current minimal wrapper:

- Exact OpenSlide error-latching behavior.
- DeepZoom helper classes.
- ICC profile / color-management parity.
- Fluorescence channel and focal-plane APIs.
- A pure-native production `read_region()`.

## Runtime Discovery Order

The loader searches for the service library in this order:

1. Explicit `sdk_lib_dir=...`.
2. Explicit `sdk_dir=...` root:
   - Windows: `bin/`, then `lib/`
   - Linux/macOS: `lib/`
3. Optional private runtime package, default name
   `opensqray_sdk_runtime`.
4. `OPENSQRAY_SDK_LIB_DIR`.
5. `OPENSQRAY_SDK_DIR` root using the same platform-specific subdirectory
   rules.

The optional runtime package may also be configured with
`OPENSQRAY_SDK_RUNTIME_PACKAGE=<package_name>`.

The default private runtime package layout is:

```text
opensqray_sdk_runtime/
  linux-x86_64/lib/
  linux-arm64/lib/
  macos-arm64/lib/
  macos-x86_64/lib/
  windows-x86_64/lib/      # supported fallback
  windows-x86_64/bin/      # package build may map this as the selected lib dir
```

For the current official SDK bundle, the observed platform roots are:

- Linux x86_64: `sqrayslide-1.2.10-linux-x64/lib`
- Linux arm64: `sqrayslide-1.2.10-linux-arm64/lib`
- macOS Apple Silicon: `sqrayslide-1.2.10-macos-arm/lib`
- Windows x86_64: `sqrayslide-1.2.10-windows-x64/bin`

macOS Intel requires a matching vendor SDK or a vendor-supported universal
runtime. OpenSqray can load `macos-x86_64` runtime packages when provided, but
it cannot manufacture a missing native SDK binary.

## Packaging Model

Recommended package split:

| Package | Visibility | Contents |
| --- | --- | --- |
| `opensqray` | public | Python source, ctypes wrapper, docs, tests, no SDK binaries |
| `opensqray-sdk-runtime-<platform>` | private/internal | Official SDK runtime libraries for one platform, if redistribution is legally allowed |
| `opensqray-sdk-runtime` | private/internal meta package | Selects or depends on the platform runtime package |

This is safer than publishing SDK binaries in the public source repository. It
also lets CI test public code without proprietary artifacts while internal
deployments install the runtime package from a private package index.

## Wheel Build Notes

Platform-specific wheel builds should apply native-library repair before
release:

- Linux: build manylinux-compatible wheels and run `auditwheel repair` if the
  SDK license allows bundling the libraries.
- macOS: use platform-specific wheels or universal2 only when the SDK binaries
  match the target architecture; repair install names/rpaths with `delocate`
  or equivalent tooling.
- Windows: include DLLs in the runtime package and register the DLL directory
  before loading the service library.

Current loader support:

- Windows DLL search directory registration via `os.add_dll_directory`.
- Linux preloads only the Sqray SDK service's required soname dependencies.
  It intentionally avoids loading every `.so` in the SDK directory because the
  official Linux bundle contains duplicate library copies such as
  `libavcodec.so`, `libavcodec.so.58`, and `libavcodec.so.58.111.100`; loading
  all of them can trigger native shutdown crashes.
- macOS skips versioned dylib aliases during preload to reduce duplicate-load
  noise.

Before any private runtime wheel is treated as usable, run the practical
validator described in [SDK Runtime Validation](sdk-runtime-validation.md). A
wheel is not validated by import success alone; it must pass region, tile,
repeat-read, parallel batch, and throughput checks on a real SDPC file.

OpenSqray also includes a static layout checker for private runtime packages:

```bash
python3 tools/check_sdk_runtime_package.py /path/to/opensqray_sdk_runtime \
  --platform-tag linux-x86_64
```

The checker verifies the platform directory and service library name without
loading native code. It is a packaging preflight, not a replacement for the real
SDK runtime validator.

## Wrapper `.so` / Native Shim Option

A thin native shim such as `libopensqray_sdk` is a reasonable later milestone.
It would export only the OpenSqray/OpenSlide-like ABI and link against the
official SDK internally. Benefits:

- Smaller public ABI surface.
- One controlled native entrypoint per platform.
- Easier integration for non-Python consumers.
- Cleaner runtime-library layout.

Limits:

- A shim does not make proprietary binaries impossible to reverse engineer.
- Legal redistribution still depends on the SDK license.
- The shim must be built and tested separately for Windows, Linux, macOS Intel,
  and macOS Apple Silicon.

Near-term recommendation: keep the Python ctypes wrapper as the source-level
contract, add private runtime wheels for deployment, then introduce a native
shim only after the Python API stabilizes.

## Security Boundary

OpenSqray should not claim binary protection as a primary security mechanism.
Use these controls instead:

- Keep SDK binaries out of the public repository.
- Distribute runtime wheels through a private package index.
- Keep license and access control outside the public package.
- Sign internal release artifacts where possible.
- Avoid exposing unnecessary SDK functions in the public Python API.

The goal is to minimize exposed surface and prevent accidental publication, not
to promise anti-reverse-engineering guarantees.
