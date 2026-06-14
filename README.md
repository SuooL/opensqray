# OpenSqray

OpenSqray is a public whole-slide image utility focused on Sqray SDPC inspection and format research. The first milestone provides a native SDPC metadata parser and a CLI. Standard whole-slide formats such as SVS are delegated to OpenSlide when the optional OpenSlide Python bindings and native library are installed.

This repository intentionally does not vendor proprietary Sqray SDK files or local sample slide data.

## Status

Alpha. Current SDPC support covers metadata inspection, heuristic associated-image JPEG candidate extraction, heuristic tile-grid candidate inspection, an OpenSlide-like SDPC facade for metadata plus raw JPEG candidate bytes, and optional Pillow decoding for candidate JPEG records. Region extraction, formal tile-index table parsing, and color correction are planned but not claimed as supported yet.

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

Optional image decoding support:

```bash
python -m pip install -e ".[image]"
```

Image decoding uses Pillow and is only needed when calling decoded image APIs.
Core SDPC metadata, JPEG record inspection, and raw JPEG byte access do not
require Pillow.

## CLI

Inspect an SDPC file:

```bash
opensqray inspect path/to/slide.sdpc
```

Include a full valid-JPEG-record scan:

```bash
opensqray inspect path/to/slide.sdpc --scan-jpegs
```

Inspect an OpenSlide-supported file such as SVS:

```bash
opensqray inspect path/to/slide.svs
```

If OpenSlide is unavailable, the CLI exits with a clear dependency message instead of trying to parse SVS itself.

List SDPC associated-image candidates:

```bash
opensqray associated path/to/slide.sdpc
```

Extract associated-image JPEG candidates without overwriting existing files:

```bash
opensqray extract-associated path/to/slide.sdpc --output-dir associated-images
```

Associated-image role names such as `label_candidate` and `macro_candidate` are
heuristic. They identify leading non-tile JPEG streams before the first
tile-sized JPEG record; they are not yet formal SDPC directory entries.

Inspect SDPC tile-grid candidates:

```bash
opensqray tile-index path/to/slide.sdpc
```

Tile coordinates are row-major candidates inferred from sequential tile-sized
JPEG records. They are useful for format research but are not yet a confirmed
SDPC tile index table.

Search for SDPC index-table diagnostic candidates:

```bash
opensqray index-research path/to/slide.sdpc
```

`index-research` scans non-JPEG byte windows before or between previewed JPEG
records for packed integer runs matching known JPEG offsets, end offsets, or
lengths. It also reports table position, small before/after hex context, and
for length-table candidates a cumulative offset reconstruction check. Matches
are diagnostic evidence for reverse engineering; they are not reported as a
parsed SDPC tile directory.

## Python API

Use `SDPCSlide` when downstream code wants OpenSlide-like metadata attributes
without requiring OpenSlide or Pillow:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    print(slide.dimensions)
    print(slide.level_dimensions)
    print(slide.level_downsamples)
    print(slide.properties["opensqray.sdpc.version"])

    label_jpeg = slide.read_associated_image_bytes("label_candidate")
    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
```

`SDPCSlide` can return raw JPEG bytes from candidate records in the current
parser preview without extra dependencies. `read_region()` intentionally raises
`NotImplementedError` until the formal SDPC tile-index table is mapped.

With the optional `image` dependency installed, candidate JPEG records can be
decoded with Pillow:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    label_image = slide.read_associated_image("label_candidate")
    tile_image = slide.read_tile_image(level=0, tile_x=0, tile_y=0)
```

Decoded tile images still come from heuristic tile candidates. They are useful
for local format research and preview tooling, but they are not a full
OpenSlide-compatible region-read implementation.

### SDPC Output Contract

SDPC inspection emits versioned JSON with `schema_version="opensqray.sdpc.metadata.v1"`. The v1 contract keeps stable metadata fields separate from research diagnostics:

* Stable fields: `version`, `file_size`, `stored_file_size`, `file_size_matches_header`, `header_size`, `level_count`, `dimensions`, `tile_size`, `thumbnail_size`, `scan_magnification`, and `metadata_offset`.
* Metadata fields: `metadata.device_id`, `metadata.acquired_at`, `metadata.scanner_model`, `metadata.objective`, and `metadata.embedded_strings`.
* Diagnostics: `experimental`, `jpeg_streams`, `field_confidence`, and `validation.warnings`.
* Associated image candidates: `associated_images.count` and `associated_images.records`.
* Tile-grid candidates: `tile_index.status`, `tile_index.levels`, `tile_index.tiles_preview`, and `tile_index.missing_tiles_preview`.

The index research diagnostic emits
`schema_version="opensqray.sdpc.index_research.v3"` and is intentionally
separate from the stable metadata contract.

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

Use `--scan-jpegs` only when you need a full valid-JPEG-record count for local research.

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
