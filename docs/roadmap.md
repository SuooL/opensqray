# OpenSqray Roadmap

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
* Keep diagnostic candidate tables separate from the stable metadata contract.
* Use ignored local samples to compare whether candidate evidence generalizes
  across SDPC versions.

M6 is complete when `opensqray index-research` reports candidate evidence with a
versioned diagnostic contract, synthetic tests cover positive and negative
cases, and local sample smoke can run without committing data.

## Phase 7: Region Reads

* Use decoded tile primitives to assemble regions once tile ordering is
  validated.
* Implement `read_region` for SDPC.
* Match OpenSlide-like coordinate conventions where practical.
* Add performance tests for large slides.

## Phase 8: Packaging and Integrations

* Decide repository license.
* Publish package artifacts if desired.
* Add examples for downstream pathology and medical AI workflows.
* Consider a plugin adapter for viewers after core parsing is stable.
