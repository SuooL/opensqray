# OpenSqray

OpenSqray is a public whole-slide image utility focused on Sqray SDPC inspection and format research. The first milestone provides a native SDPC metadata parser and a CLI. Standard whole-slide formats such as SVS are delegated to OpenSlide when the optional OpenSlide Python bindings and native library are installed.

This repository intentionally does not vendor proprietary Sqray SDK files or local sample slide data.

## Status

Alpha. Current SDPC support is metadata-only and format-research oriented. Pixel reads, region extraction, tile coordinate mapping, and color correction are planned but not claimed as supported yet.

## Install

For local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Optional OpenSlide support:

```bash
python -m pip install -e ".[openslide]"
```

You also need the native OpenSlide library available on your system for SVS and other OpenSlide-backed formats.

## CLI

Inspect an SDPC file:

```bash
opensqray inspect path/to/slide.sdpc
```

Include a full JPEG marker scan:

```bash
opensqray inspect path/to/slide.sdpc --scan-jpegs
```

Inspect an OpenSlide-supported file such as SVS:

```bash
opensqray inspect path/to/slide.svs
```

If OpenSlide is unavailable, the CLI exits with a clear dependency message instead of trying to parse SVS itself.

### SDPC Output Contract

SDPC inspection emits versioned JSON with `schema_version="opensqray.sdpc.metadata.v1"`. The v1 contract keeps stable metadata fields separate from research diagnostics:

* Stable fields: `version`, `file_size`, `stored_file_size`, `file_size_matches_header`, `header_size`, `level_count`, `dimensions`, `tile_size`, `thumbnail_size`, `scan_magnification`, and `metadata_offset`.
* Metadata fields: `metadata.device_id`, `metadata.acquired_at`, `metadata.scanner_model`, `metadata.objective`, and `metadata.embedded_strings`.
* Diagnostics: `experimental`, `jpeg_streams`, `field_confidence`, and `validation.warnings`.

`file_size_matches_header=false` is reported as a validation warning, not a hard parse failure.

## Development

Run tests with the standard library test runner:

```bash
python3 -m unittest discover -s tests
```

The tests use synthetic fixtures. Do not commit local whole-slide samples.

To validate ignored local SDPC samples under `data/` without copying or committing them:

```bash
python3 tools/validate_local_samples.py --compact
```

Use `--scan-jpegs` only when you need a full JPEG marker count for local research.

## Git Flow

Development follows feature PR -> dev PR:

1. Create work on `feature/<topic>`.
2. Open feature PR into `dev`.
3. After integration, open `dev` PR into `main`.
4. Keep `main` as the public release branch.

## Excluded Local Artifacts

The following are intentionally ignored:

* `sqrayslide_20251128_x64/` - internal SDK bundle.
* `data/` - local slide samples.
* local assistant/workflow directories such as `.codex/`, `.claude/`, `.agents/`, and `.trellis/`.

## License

No license has been selected yet. Until the repository owner adds a license, public visibility does not grant reuse rights.
