# OpenSqray

[![CI](https://github.com/SuooL/opensqray/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SuooL/opensqray/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)

**Language**: [简体中文](README.md) | English

**Tutorial**: [Jupyter Tutorial](examples/opensqray_tutorial.ipynb)

OpenSqray is a Python toolkit for whole-slide pathology images. Its current focus is public-safe Sqray SDPC inspection, metadata parsing, candidate JPEG extraction, and SDK-backed OpenSlide-like pixel reads. For common WSI formats such as SVS, OpenSqray delegates inspection to optional OpenSlide bindings instead of implementing a separate parser.

The project is designed around explicit boundaries: parse what can be parsed natively, label reverse-engineering evidence as diagnostic, and delegate coordinate-accurate pixel reads to a locally configured official SDK runtime when needed.

## Features

- Native SDPC metadata parsing: dimensions, level count, tile size, thumbnail size, magnification, and scanner-related strings.
- Embedded JPEG record scanning with basic structure validation to reduce false positives.
- Associated-image candidates for label/macro-style embedded JPEG resources.
- Tile-index research utilities for row-major tile candidates and diagnostic index-table evidence.
- `OpenSqraySlide`: an SDK-backed OpenSlide-like SDPC class supporting `read_region()`, `get_thumbnail()`, `associated_images`, level metadata, and properties.
- Research-oriented `SDPCSlide` facade exposing metadata, candidate JPEG bytes, and lower-level SDK tile/region access.
- Optional Pillow decoding via `opensqray[image]`.
- Optional Sqray SDK backend for reliable SDPC tile JPEG and BGRA region reads when a licensed runtime is available locally.
- Optional OpenSlide backend for SVS and other OpenSlide-supported formats.

## Preview

![OpenSqray API demo](docs/assets/opensqray-api-demo.svg)

The visual above is a synthetic, public-safe flow diagram showing the typical OpenSqray path: native parsing for metadata and candidate-resource research, and the SDK backend for coordinate-accurate tile/region reads.

The images below are real associated-image exports from the public SDPC sample `20220514_145829_0.sdpc`, generated directly with `opensqray extract-associated`. Candidate names remain heuristic and do not imply confirmed official SDPC directory entries.

| `label_candidate` | `macro_candidate` |
| --- | --- |
| <img src="docs/assets/20220514_145829_0-0000-label_candidate.jpg" alt="Real SDPC label candidate" width="280"> | <img src="docs/assets/20220514_145829_0-0001-macro_candidate.jpg" alt="Real SDPC macro candidate" width="520"> |

The image below is real SDK-backed `OpenSqraySlide.read_region((14000, 3600), 0, (512, 512))` output, demonstrating the OpenSlide-like region-read path for SDPC:

![Real SDK-backed SDPC region](docs/assets/20220514_145829_0-sdk-region-512.png)

For a reproducible real-file walkthrough, open [examples/opensqray_tutorial.ipynb](examples/opensqray_tutorial.ipynb). The notebook reads local `data/20220514_145829_0.sdpc` by default, can be pointed at another SDPC file with `OPENSQRAY_TUTORIAL_SDPC=/path/to/file.sdpc`, and runs the OpenSqray parser, `SDPCSlide`, and CLI against it. The public repository does not distribute real slide files from `data/`; if you clone from GitHub, provide your own local SDPC file before running the notebook.

## Installation

Install from source:

```bash
git clone https://github.com/SuooL/opensqray.git
cd opensqray
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Optional image decoding:

```bash
python -m pip install -e ".[image]"
```

Optional OpenSlide Python bindings:

```bash
python -m pip install -e ".[openslide]"
```

OpenSlide-backed formats such as SVS also require the native OpenSlide library on your system.

Optional Sqray SDK backend:

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib
# or:
export OPENSQRAY_SDK_DIR=/path/to/sqrayslide
```

If the SDK runtime needs additional native-library directories:

```bash
export OPENSQRAY_SDK_EXTRA_LIB_DIRS=/path/to/extra/libs
```

On macOS, the current Sqray SDK package requires dynamic-library paths before Python starts:

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib
export DYLD_LIBRARY_PATH="$OPENSQRAY_SDK_LIB_DIR:/path/to/libomp/lib:${DYLD_LIBRARY_PATH:-}"
```

OpenSqray does not vendor, redistribute, or repackage proprietary SDK binaries.

## Quick Start

Inspect SDPC metadata:

```bash
opensqray inspect path/to/slide.sdpc --compact
```

List associated-image candidates:

```bash
opensqray associated path/to/slide.sdpc --compact
```

Export associated-image candidate JPEGs:

```bash
opensqray extract-associated path/to/slide.sdpc \
  --output-dir associated-images
```

Inspect tile-grid candidates:

```bash
opensqray tile-index path/to/slide.sdpc \
  --preview-limit 30 \
  --compact
```

Read a native candidate tile JPEG:

```bash
opensqray read-tile path/to/slide.sdpc \
  --backend native \
  --preview-limit 100 \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-native.jpg
```

Read a tile through the SDK backend:

```bash
opensqray read-tile path/to/slide.sdpc \
  --backend sdk \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-sdk.jpg
```

Inspect an OpenSlide-supported file such as SVS:

```bash
opensqray inspect path/to/slide.svs --compact
```

If OpenSlide is unavailable, the CLI returns a clear dependency message instead of trying to parse SVS as SDPC.

## Python API

Use SDK-backed `OpenSqraySlide` for practical OpenSlide-like SDPC reading:

```python
from opensqray import OpenSqraySlide

with OpenSqraySlide("path/to/slide.sdpc") as slide:
    print(slide.dimensions)
    print(slide.level_count)
    print(slide.level_dimensions)
    print(slide.level_downsamples)
    print(slide.properties["openslide.mpp-x"])

    region = slide.read_region((0, 0), 0, (512, 512))
    thumbnail = slide.get_thumbnail((512, 512))
    label = slide.associated_images["label"]

    region.save("region.png")
    thumbnail.save("thumbnail.jpg")
```

Use `open_slide()` when you want one entrypoint for SDPC and OpenSlide-backed SVS:

```python
from opensqray import open_slide

with open_slide("path/to/slide.sdpc") as slide:
    region = slide.read_region((0, 0), 0, (512, 512))
```

Native SDPC metadata and candidate JPEG bytes:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    print(slide.dimensions)
    print(slide.level_dimensions)
    print(slide.level_downsamples)
    print(slide.properties["opensqray.backend"])

    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
```

Decode candidate JPEGs with `opensqray[image]` installed:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    tile_image = slide.read_tile_image(level=0, tile_x=0, tile_y=0)
```

SDK-backed region reads:

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc", backend="sdk") as slide:
    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
    region_bgra = slide.read_region_bgra_bytes((0, 0), 0, (512, 512))
    region_image = slide.read_region((0, 0), 0, (512, 512))
```

`read_region()` converts SDK BGRA bytes into a Pillow RGBA image and therefore requires `opensqray[image]`.

## Backend Coverage

OpenSqray currently has two SDPC paths:

- `backend="native"`: public parser path with no proprietary runtime dependency. It is useful for metadata, associated-image candidates, tile/index research, and preview-limited tile JPEG byte reads.
- `OpenSqraySlide` / `backend="sdk"`: official-runtime adapter and the practical SDPC reading path for coordinate-accurate tile JPEGs, region reads, thumbnails, and associated images.

| Capability | Native backend | SDK backend |
| --- | --- | --- |
| SDPC metadata / properties | Supported | Supported, with OpenSlide-style properties |
| Level dimensions / downsamples | Inferred from parsed metadata | Supported; `OpenSqraySlide` reports OpenSlide-style downsamples |
| Associated images | Heuristic JPEG candidates | Supports `label` / `thumbnail` / `macro` |
| Tile JPEG by coordinate | Heuristic and preview-limited | Supported |
| `read_region_bgra_bytes()` | Not implemented | Supported |
| `read_region()` | Raises `NotImplementedError` | Supported when Pillow is installed |
| `get_thumbnail()` | Not implemented | Supported |
| `get_best_level_for_downsample()` | Not implemented | Supported with OpenSlide-style downsample selection |
| Color correction / ICC | Not implemented | SDK has an API; not yet exposed with OpenSlide ICC semantics |
| Fluorescence / channels / focal planes | Not implemented | Not wrapped yet |
| Full OpenSlide API parity | Not yet | Core reading API is usable; error-latching, DeepZoom, and ICC remain roadmap items |

Bottom line: use `OpenSqraySlide` with a configured official Sqray SDK runtime when you need SDPC to behave like an OpenSlide-readable WSI. The native backend remains a public-safe metadata and format-research path, not the production pixel-reading path.

## Output Contracts

SDPC inspection emits versioned JSON with the current schema:

```text
opensqray.sdpc.metadata.v1
```

Stable metadata and research diagnostics are kept separate so downstream code does not treat reverse-engineering evidence as a confirmed file-format contract. `index-research` uses a separate schema:

```text
opensqray.sdpc.index_research.v4
```

Diagnostic results are for format research and should not be treated as a complete parsed SDPC tile directory.

## Roadmap

- [x] Project scaffold, CLI, and synthetic fixture tests.
- [x] SDPC metadata parser with versioned JSON output.
- [x] Associated-image candidate discovery and extraction.
- [x] Tile-grid candidates and index-research diagnostics.
- [x] `SDPCSlide` facade, Pillow decode adapter, and SDK backend MVP.
- [x] SDK-backed `OpenSqraySlide` compatibility layer: `read_region()`, `get_thumbnail()`, associated images, and level metadata.
- [ ] More complete SDPC tile-directory mapping and cross-sample validation.
- [ ] OpenSlide error-latching, DeepZoom helpers, and ICC/color correction support.
- [ ] Private deployment guidance for SDK runtime packaging.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Tests use synthetic fixtures and do not require real slide data or proprietary SDK binaries.

## Data and Security Boundary

The public repository contains source code, synthetic test fixtures, documentation, and lightweight preview images extracted from a public SDPC sample. It does not contain complete real slide files, patient-identifiable data, proprietary SDK binaries, or non-public implementation code. Configure a licensed SDK runtime in your own environment if you need the SDK backend.

## Acknowledgements

OpenSqray's SDPC research and engineering design references the public work of [OpenSDPC](https://github.com/WonderLandxD/opensdpc). OpenSqray does not copy or redistribute its code; format observations and implementation boundaries are kept explicit.

## License

No open-source license has been selected yet. Public visibility does not grant permission to use, copy, distribute, or modify the code until the repository owner adds a license.
