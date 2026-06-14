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

## Phase 4: Region Reads

* Add tile decoding through a public dependency such as Pillow.
* Implement `read_region` for SDPC.
* Match OpenSlide-like coordinate conventions where practical.
* Add performance tests for large slides.

## Phase 5: Packaging and Integrations

* Decide repository license.
* Publish package artifacts if desired.
* Add examples for downstream pathology and medical AI workflows.
* Consider a plugin adapter for viewers after core parsing is stable.
