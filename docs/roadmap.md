# OpenSqray Roadmap

This roadmap distinguishes implemented capabilities, validated environments,
and remaining product work. Do not treat diagnostic native parsing milestones
as production SDPC pixel-read support; production SDPC image reads currently go
through the optional Sqray SDK-backed `OpenSqraySlide` path.

## Current Status

### Implemented

* Public-safe SDPC metadata parser and CLI.
* Embedded JPEG scanning, associated-image candidates, and safe extraction.
* Candidate tile-grid preview and `index-research` diagnostics.
* `SDPCSlide` facade for native metadata, candidate JPEG bytes, and optional
  SDK-backed low-level reads.
* Pillow-backed optional image adapter.
* SDK-backed `OpenSqraySlide` with OpenSlide-like core APIs:
  `dimensions`, `level_count`, `level_dimensions`, `level_downsamples`,
  `properties`, `associated_images`, `read_region()`, `get_thumbnail()`,
  `get_best_level_for_downsample()`, and `read_tile_jpeg_bytes()`.
* Batch patch helpers: `RegionRequest`, `iter_patch_requests()`,
  `read_regions()`, `iter_regions()`, `OpenSqraySlide.read_regions()`, and
  `OpenSqraySlide.iter_regions()`.
* Practical SDK runtime validator and sanitized validation summaries for real
  SDPC files.
* Runtime packaging strategy docs and high-throughput patch extraction plan.
* Static private runtime package layout checker, runtime staging helper, and
  runtime-root discovery through `OPENSQRAY_SDK_RUNTIME_ROOT`.
* Private runtime wheel builder for staged SDK runtime package roots.
* OpenSlide compatibility matrix documenting supported, partial, and unclaimed
  behavior.

### Validated

* CI unit tests pass on Python 3.10, 3.11, and 3.12.
* macOS Apple Silicon was locally validated with the official SDK runtime and
  public `20220514_145829_0.sdpc` sample.
* Linux x86_64 was validated on Ubuntu with source synced from GitHub `dev`,
  the official Linux SDK runtime, and public `20220514_145829_0.sdpc` sample.
  The validator passed with `errors=[]`, repeated-read consistency, parallel
  consistency, and exit code `0`.

### Not Yet Validated

* Windows x86_64 real SDK runtime validation.
* Linux arm64 real SDK runtime validation.
* macOS Intel real SDK runtime validation, pending a vendor-supported x86_64 or
  universal runtime.
* Private runtime wheels or a native shim package.

### Deliberately Not Claimed

* Full native SDPC tile-directory parsing.
* Native `SDPCSlide.read_region()` without the SDK.
* Exact full OpenSlide API parity, including OpenSlide error-latching,
  DeepZoom helpers, ICC/color-management parity, and multi-channel/focal-plane
  APIs.

## Phase 1: Public Hygiene and Metadata MVP

* Exclude internal SDKs and local slide samples from git.
* Add Python package scaffold and CLI.
* Define a versioned SDPC metadata JSON contract.
* Parse SDPC core header fields:
  * version signature
  * file-size consistency
  * pyramid level count
  * level-0 dimensions
  * tile dimensions
  * thumbnail dimensions
  * scan magnification
  * fixed metadata strings
* Delegate SVS and other non-SDPC whole-slide formats to OpenSlide.
* Add synthetic fixture tests.
* Add ignored local-sample smoke validation for `data/*.sdpc`.

M1 is complete when the parser emits `opensqray.sdpc.metadata.v1`, synthetic
tests cover core fields and warning behavior, and ignored local SDPC samples can
be validated without entering git history.

## Phase 2: SDPC Associated Images

* Identify valid embedded JPEG records and filter false positive marker hits.
* Classify leading non-tile JPEG streams as associated-image candidates.
* Add safe extraction APIs and CLI commands for associated-image candidates.
* Validate candidate detection on ignored local SDPC samples.

M2 is complete when `opensqray associated` lists candidate records,
`opensqray extract-associated` writes JPEG candidates without overwriting by
default, and local smoke validation reports candidate summaries for ignored
`data/*.sdpc` samples.

## Phase 3: Tile Index Reconstruction

* Infer expected pyramid-level grids from level-0 dimensions, tile size, and level count.
* Map sequential tile-sized JPEG records to row-major candidate tile coordinates.
* Define explicit candidate behavior for missing tiles, edge valid sizes, and preview-limited scans.
* Keep formal SDPC tile-index table parsing as future work until the directory/index records are located.

M3 is complete when `opensqray tile-index` exposes candidate levels and tile
previews, synthetic tests cover row-major mapping and missing tile behavior, and
local sample validation reports tile-index status without committing samples.

## Phase 4: Slide Facade and Region-Read Preparation

* Add `SDPCSlide` as an OpenSlide-like facade for SDPC metadata.
* Expose `dimensions`, `level_count`, `level_dimensions`, `level_downsamples`,
  `properties`, and associated-image candidate records.
* Provide raw JPEG byte access for associated-image candidates and tile
  candidates in the current parser preview.
* Keep `read_region` explicitly unsupported until pixel decoding and formal
  tile-index parsing are ready.

M4 is complete when the facade is covered by synthetic tests, can smoke against
ignored local samples without committing data, and documents that tile
coordinates remain heuristic.

## Phase 5: Optional Image Decoding

* Add a Pillow-backed optional image adapter without making core SDPC parsing
  depend on Pillow.
* Decode associated-image candidates and tile JPEG candidates through
  `SDPCSlide`.
* Keep decoded tile images labeled as heuristic candidates until formal
  tile-index parsing is complete.

M5 is complete when decoded candidate-image APIs are covered by dependency-free
tests, missing Pillow reports a clear error, and local smoke validation still
works without installing Pillow.

## Phase 6: Formal Index Research

* Add diagnostics for locating SDPC index-like tables by matching packed JPEG
  record offsets, end offsets, and lengths in non-JPEG byte windows.
* Add candidate table context fields so runs can be inspected in their
  surrounding binary structure.
* Validate whether packed length-table candidates can reconstruct preview JPEG
  offsets through cumulative byte lengths.
* Keep diagnostic candidate tables separate from the stable metadata contract.
* Use ignored local samples to compare whether candidate evidence generalizes
  across SDPC versions.

M6 is complete when `opensqray index-research` reports candidate evidence with a
versioned diagnostic contract, synthetic tests cover positive and negative
cases, and local sample smoke can run without committing data.

## Phase 7: SDK-Backed OpenSlide Compatibility

* Add `OpenSqraySlide` as the practical SDPC pixel-reading class backed by a
  locally configured official Sqray SDK runtime.
* Expose OpenSlide-like `dimensions`, `level_count`, `level_dimensions`,
  `level_downsamples`, `properties`, `associated_images`, `read_region()`,
  `get_thumbnail()`, and `get_best_level_for_downsample()`.
* Keep OpenSlide-style downsample semantics in the compatibility layer even
  when raw SDK scale values use inverse or vendor-specific conventions.
* Keep native parsing as metadata / format-research support rather than a
  production SDPC `read_region()` path.
* Validate real SDK reads against ignored local SDPC samples without committing
  SDK binaries or full slide data.

M7 is complete when `OpenSqraySlide` can read real SDPC regions and thumbnails
through the SDK backend, CI covers the wrapper with fake SDK tests, and README
shows the SDK-backed path as the production SDPC pixel-read path.

## Phase 8: Runtime Packaging and Batch Patch Reads

* Add runtime-loader support for explicit SDK library directories, SDK roots,
  optional private runtime packages, and environment variables.
* Handle platform-specific SDK layouts:
  * Windows service DLLs under `bin/`
  * Linux versioned shared libraries such as `.so.17`
  * macOS dylib preload behavior and documented `DYLD_LIBRARY_PATH` caveats
* Add batch patch helpers:
  * `RegionRequest`
  * `iter_patch_requests()`
  * `read_regions()`
  * `OpenSqraySlide.read_regions()`
* Use one slide handle per worker for parallel reads until the vendor SDK
  documents shared-handle thread safety.
* Add practical SDK runtime validation that checks region reads, tile JPEGs,
  repeated-read stability, serial-vs-parallel batch consistency, and throughput
  on real SDPC files.
* Document private SDK runtime wheel strategy and large-scale patch extraction
  guidance.

M8 is complete when batch patch APIs have unit tests, the loader can discover a
private runtime package without vendoring binaries in the public repo, practical
runtime validation exists, and docs describe the cross-platform packaging,
validation, and throughput strategy.

## Completed Research Milestones

### M9: Length-Table Reconstruction Diagnostics

* Extend `index-research` so length-table candidates report whether cumulative
  byte lengths reproduce observed preview JPEG offsets and end offsets.
* Keep this under the diagnostic `index-research` schema, not the stable SDPC
  metadata schema.
* Add synthetic positive and negative tests:
  * adjacent JPEG tile records reconstruct cleanly
  * non-adjacent JPEG records do not get over-claimed
* Validate against ignored local samples, especially `N067102_8.sdpc`.

M9 is complete when the v3+ diagnostic contract exposes length reconstruction
evidence, tests cover reconstruction and mismatch cases, and local smoke confirms
the observation without committing sample data.

Status: complete for the diagnostic contract. The current schema is
`opensqray.sdpc.index_research.v4`, with synthetic positive/negative tests.

### M10: Formal Tile Directory Candidate Research

* Extend length-table diagnostics so the byte extent from a candidate table to
  the current non-JPEG window boundary is compared with expected pyramid-level
  tile counts.
* Inspect the byte range around confirmed length tables to identify neighboring
  fields that may encode tile count, level, row/column, plane/channel, or table
  boundaries.
* Compare at least two local SDPC files and any future public-safe synthetic
  patterns before promoting a field from diagnostic to experimental.
* Consult the local official SDK headers only for API semantics such as
  coordinate systems, tile dimensions, level counts, and returned image formats;
  do not copy or expose proprietary implementation details.
* Write a public-safe research note describing observed structures and negative
  findings.

M10 is complete when OpenSqray can name the most plausible directory/table
segments and explain what is still unknown without claiming a full parser.

Status: partially complete as public-safe diagnostics. OpenSqray reports the
most plausible length-table evidence and limitations, but it does not yet
promote those diagnostics to a parsed native tile directory.

## Remaining Development Plan

### M11: Confirmed Native Tile Map Prototype

* Build an experimental tile-map object only after directory/table evidence
  links JPEG byte ranges to level and tile matrix coordinates.
* Cross-check expected level grids, candidate table lengths, reconstructed
  offsets, and record dimensions.
* Add synthetic tests for sparse tiles, edge tiles, preview-limited scans, and
  invalid/mismatched tables.
* Keep the existing heuristic row-major tile preview as a fallback diagnostic,
  clearly separated from any parsed table.
* Validate against at least two real SDPC samples:
  * public `20220514_145829_0.sdpc`
  * ignored internal `N067102_8.sdpc` or another large local slide
* Fail closed when table evidence is incomplete, contradictory, or only
  preview-limited.

M11 is complete when native parsed/experimental tile maps can be produced for
validated samples while failing closed when table evidence is incomplete or
contradictory.

### M12: Native Pixel Access and Region Assembly

* Use parsed tile maps and optional image decoding to assemble `read_region`.
* Match OpenSlide-like top-left coordinate conventions where practical.
* Handle edge padding, level selection, bounds, and missing-tile behavior
  explicitly.
* Add tests for tile-aligned reads, cross-tile reads, edge reads, and unsupported
  dependency paths.
* Keep color correction out of the first region-read implementation unless a
  public-safe, testable correction path is identified.
* Keep SDK-backed `OpenSqraySlide` as the production read path until native
  assembly matches the same coordinate and image-size expectations.

M12 is complete when native `SDPCSlide.read_region()` works from a confirmed tile
map, has focused tests, and no longer depends on heuristic tile order.

### M13: Cross-Platform Runtime Validation

* Run the practical SDK validator on Windows x86_64 using the official SDK
  `bin/` layout.
* Run the practical SDK validator on Linux arm64 using the official SDK `lib/`
  layout.
* Run macOS Intel validation only when a matching vendor runtime exists.
* Store validation summaries outside the public repository or in sanitized
  release notes; do not commit SDK binaries or full slide data.
* Keep source sync for remote validation through GitHub branches and PRs.
  `data/` and `sqrayslide_20251128_x64/` remain local ignored assets.
* Use `tools/validate_sdk_runtime.py --summary-output` for sanitized platform
  summaries.

M13 is complete when the validation matrix has real pass/fail evidence for
every supported platform instead of design-only claims.

### M14: Private Runtime Packaging and Native Shim

* Decide repository license.
* Build private platform runtime wheels only if SDK redistribution terms allow
  it.
* Consider a thin native shim after the Python wrapper API stabilizes.
* Package only the minimal runtime dependency set needed by the service
  library, not the entire vendor SDK tree.
* Use `tools/stage_sdk_runtime_package.py` to stage selected runtime libraries
  into an external private runtime package layout.
* Use `OPENSQRAY_SDK_RUNTIME_ROOT` to validate staged/private runtime package
  roots without manually selecting the platform `lib/` or `bin/` directory.
* Use `tools/build_sdk_runtime_wheel.py` to create one private platform wheel
  from a staged runtime root.
* Run `tools/check_sdk_runtime_package.py` before building or publishing an
  internal runtime wheel.
* Run the practical validator against every runtime wheel or shim artifact.

M14 is complete when private runtime artifacts can be installed without manual
SDK path setup and pass the same real-SDPC validation checks.

### M15: OpenSlide Parity Extensions

* Decide which OpenSlide compatibility gaps are worth implementing for SDPC:
  error-latching semantics, DeepZoom helpers, ICC/color management, and
  optional multi-channel/focal-plane APIs.
* Maintain `docs/openslide-compatibility.md` as the compatibility source of
  truth.
* Add only APIs with clear semantics on SDPC and tests that can run without
  publishing proprietary data.
* Keep non-SDPC formats delegated to OpenSlide.

M15 is complete when OpenSqray either implements or explicitly declines each
major OpenSlide parity gap with documented reasoning.

### M16: Release and Integrations

* Publish package artifacts if desired.
* Add examples for downstream pathology and medical AI workflows.
* Consider a plugin adapter for viewers after core parsing is stable.

M16 is complete when `dev` is intentionally promoted to `main`, a SemVer tag and
GitHub Release are created, and release notes clearly state SDPC support
boundaries.

## Execution Order

1. M13: complete real cross-platform SDK validation first. This protects the
   current usable product path.
2. M14: build private runtime packaging only after the validation matrix is
   stable enough to catch packaging regressions.
3. M15: fill OpenSlide parity gaps according to real downstream demand.
4. M11-M12: continue native SDPC tile-map and region-read research in parallel,
   but do not block SDK-backed production use on full native parsing.
5. M16: promote releases from `dev` to `main` only when the current milestone
   has fresh validation evidence.
