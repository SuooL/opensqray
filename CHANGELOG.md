# Changelog

## v0.3.0

### Added

- SDK runtime staging with `tools/stage_sdk_runtime_package.py`.
- Static SDK runtime package checking with manifest-aware staging docs.
- `OPENSQRAY_SDK_RUNTIME_ROOT` discovery for staged/private runtime package
  roots.
- Private SDK runtime wheel builder with `tools/build_sdk_runtime_wheel.py`.
- OpenSlide-like `detect_format()` for SDPC and OpenSlide-delegated formats.
- `OpenSqrayDeepZoomGenerator` for DeepZoom-style tile serving through
  existing `read_region()` support.
- Chunked `iter_regions()` patch reading and stronger SDK runtime validation
  summaries.

### Validation

- CI passes on Python 3.10, 3.11, and 3.12.
- macOS Apple Silicon real SDK validation passed on the public
  `20220514_145829_0.sdpc` sample.
- Linux x86_64 real SDK validation passed on Ubuntu from GitHub-synced source,
  including staged runtime roots and private runtime wheel extraction.

### Boundaries

- Windows x86_64, Linux arm64, and macOS Intel real SDK runtime validation are
  not yet complete.
- Native SDPC `read_region()` without the official SDK remains intentionally
  unsupported until the SDPC tile directory is fully proven.
- SDK binaries, full slide data, and private runtime wheels are not distributed
  in the public repository.

## v0.2.0

- SDK-backed `OpenSqraySlide` compatibility layer for practical SDPC
  `read_region()`, thumbnails, associated images, and level metadata.
- Batch patch reading helpers and runtime validation tooling.
- Public-safe SDPC metadata, associated-image, tile-preview, and index-research
  diagnostics.
