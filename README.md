# OpenSqray

OpenSqray is a public whole-slide image utility focused on Sqray SDPC inspection and format research. The first milestone provides a native SDPC metadata parser and a CLI. Standard whole-slide formats such as SVS are delegated to OpenSlide when the optional OpenSlide Python bindings and native library are installed.

This repository intentionally does not vendor proprietary Sqray SDK files or local sample slide data.

## Status

Alpha. Current SDPC support covers metadata inspection, heuristic associated-image JPEG candidate extraction, heuristic tile-grid candidate inspection, an OpenSlide-like SDPC facade for metadata plus raw JPEG candidate bytes, optional Pillow decoding, and an optional Sqray SDK backend for reliable SDPC tile JPEG and BGRA region reads when a local SDK runtime is configured. Formal native tile-index table parsing and color correction are still research work.

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

Optional Sqray SDK backend:

OpenSqray does not vendor or redistribute proprietary Sqray SDK binaries. If
you have a licensed SDK runtime locally, point OpenSqray at its library
directory:

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib
# or:
export OPENSQRAY_SDK_DIR=/path/to/sqrayslide
```

If the runtime needs extra native-library directories, set:

```bash
export OPENSQRAY_SDK_EXTRA_LIB_DIRS=/path/to/extra/libs
```

On macOS and Linux, the platform dynamic-library search path may still need to
include the SDK directory for transitive dependencies. For private deployment,
prefer a private wheel or Docker image that contains the SDK runtime with
platform-appropriate rpaths/install names.

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
for length-table candidates cumulative offset reconstruction and table-extent
checks. Matches are diagnostic evidence for reverse engineering; they are not
reported as a parsed SDPC tile directory.

Inspect geometry through a locally configured Sqray SDK runtime:

```bash
opensqray sdk-info path/to/slide.sdpc
```

Write one tile JPEG through the native candidate backend:

```bash
opensqray read-tile path/to/slide.sdpc \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile.jpg
```

Write one tile JPEG through the official SDK backend:

```bash
opensqray read-tile path/to/slide.sdpc \
  --backend sdk \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile.jpg
```

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

Use the optional SDK backend for reliable SDPC tile coordinates and region
reads when the official runtime is locally available:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc", backend="sdk") as slide:
    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
    region_bgra = slide.read_region_bgra_bytes((0, 0), 0, (512, 512))
```

With the optional `image` dependency installed, SDK-backed `read_region()`
returns a Pillow image converted from the SDK's BGRA bytes:

```python
with SDPCSlide("path/to/slide.sdpc", backend="sdk") as slide:
    region_image = slide.read_region((0, 0), 0, (512, 512))
```

The SDK backend is an adapter over a local official runtime. Its native
libraries remain outside the public repository.

## Backend API Coverage

OpenSqray aims to provide an OpenSlide-like user experience for SDPC files, but
the native backend is not yet equivalent to the official Sqray SDK or a full
OpenSlide backend. Today there are two SDPC paths:

* `backend="native"` is the public parser path. It has no proprietary runtime
  dependency and is suitable for metadata inspection, associated-image
  candidates, tile-index research, and preview-limited raw JPEG candidate
  reads.
* `backend="sdk"` is the opt-in official-runtime adapter. It is the current
  reliable path for SDK-backed tile JPEG reads and BGRA region reads.

| Capability | Native backend | SDK backend |
| --- | --- | --- |
| Metadata/properties | Supported | Supported, with SDK geometry available through `sdk-info` |
| Level dimensions/downsamples | Inferred from parsed metadata | SDK-reported |
| Associated images | Heuristic JPEG candidates | Not wrapped yet |
| Tile JPEG by coordinate | Heuristic, preview-limited candidates | Supported through the SDK |
| `read_region_bgra_bytes()` | Not implemented | Supported through the SDK |
| `read_region()` | Raises `NotImplementedError` | Supported when Pillow is installed |
| Color correction | Not implemented | SDK may support it, but OpenSqray does not wrap it yet |
| Fluorescence/channels/focal planes | Not implemented | SDK may support them, but OpenSqray does not wrap them yet |
| Full OpenSlide API parity | Not yet | Partial practical parity for tile and region reads |

In short: native SDPC support is useful and public-safe, but it should not be
treated as a production replacement for the official SDK's pixel APIs yet. Use
the SDK backend when downstream code needs coordinate-accurate tile reads or
OpenSlide-style region reads.

## Quick API Tutorial

Native metadata and candidate-tile workflow:

```bash
opensqray inspect path/to/slide.sdpc --compact
opensqray tile-index path/to/slide.sdpc --preview-limit 30 --compact
opensqray read-tile path/to/slide.sdpc \
  --backend native \
  --preview-limit 100 \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-native.jpg
```

This path reads from candidate JPEG records discovered by the parser preview.
It is useful for research and smoke checks, but it is not a full native
`read_region()` implementation.

SDK-backed workflow:

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib

opensqray sdk-info path/to/slide.sdpc --compact
opensqray read-tile path/to/slide.sdpc \
  --backend sdk \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-sdk.jpg
```

Python native metadata and candidate bytes:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    print(slide.dimensions)
    print(slide.level_dimensions)
    print(slide.properties["opensqray.backend"])

    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
```

Python SDK-backed tile and region reads:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc", backend="sdk") as slide:
    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
    region_bgra = slide.read_region_bgra_bytes((0, 0), 0, (512, 512))
    region_image = slide.read_region((0, 0), 0, (512, 512))
    region_image.save("region.png")
```

`read_region()` requires Pillow because OpenSqray converts the SDK's BGRA bytes
to an RGBA image object.

Example observed on one local ignored SDPC sample:

```json
{
  "backend": "sqray_sdk",
  "tile_size": {"width": 544, "height": 448},
  "level_count": 7,
  "level0_grid": {"columns": 92, "rows": 208}
}
```

The same sample produced a level-0 tile JPEG for `(tile_x=0, tile_y=0)` with
`19805` bytes through the SDK backend. Native candidate bytes matched this tile
in the local research preview for that sample, but this remains validation
evidence, not a guarantee of complete native API parity.

### SDPC Output Contract

SDPC inspection emits versioned JSON with `schema_version="opensqray.sdpc.metadata.v1"`. The v1 contract keeps stable metadata fields separate from research diagnostics:

* Stable fields: `version`, `file_size`, `stored_file_size`, `file_size_matches_header`, `header_size`, `level_count`, `dimensions`, `tile_size`, `thumbnail_size`, `scan_magnification`, and `metadata_offset`.
* Metadata fields: `metadata.device_id`, `metadata.acquired_at`, `metadata.scanner_model`, `metadata.objective`, and `metadata.embedded_strings`.
* Diagnostics: `experimental`, `jpeg_streams`, `field_confidence`, and `validation.warnings`.
* Associated image candidates: `associated_images.count` and `associated_images.records`.
* Tile-grid candidates: `tile_index.status`, `tile_index.levels`, `tile_index.tiles_preview`, and `tile_index.missing_tiles_preview`.

The index research diagnostic emits
`schema_version="opensqray.sdpc.index_research.v4"` and is intentionally
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
