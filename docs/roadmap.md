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

* Identify label, macro, and thumbnail JPEG records.
* Add safe extraction APIs for associated images.
* Validate on more SDPC versions.

## Phase 3: Tile Index Reconstruction

* Locate and document tile index tables.
* Map JPEG streams to pyramid levels and tile coordinates.
* Add tests covering sparse and non-full-scan SDPC files.
* Define explicit behavior for missing edge tiles and padded regions.

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
