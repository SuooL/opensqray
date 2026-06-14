# SDPC Format Notes

These notes are based on local binary inspection of SDPC samples and are safe for public documentation. They do not copy proprietary SDK implementation code.

## Confirmed Observations

Observed SDPC signatures:

* `SQ1.1.9.0430`
* `SQ1.0.0.0620`

Both inspected files contain embedded JPEG streams identifiable by `ff d8 ff`
candidate markers followed by parseable JPEG structure. The first valid JPEG
record was found at byte offset `7855` in both local samples.

The fixed metadata block was observed at offset `0x1b34` in both samples and includes device, acquisition-time, scanner, and objective strings.

## Header Field Map

Offsets are little-endian and currently sample-validated, not a formal specification.

| Offset | Type | Meaning | Confidence |
|---|---:|---|---|
| `0x00` | 12-byte ASCII | SDPC version signature | high |
| `0x12` | uint32 | main header size, observed `156` | high |
| `0x16` | uint32 | file size in bytes | high |
| `0x26` | uint32 | pyramid level count | high |
| `0x2a` | uint32 | level-0 width | high |
| `0x2e` | uint32 | level-0 height | high |
| `0x32` | uint32 | tile width | high |
| `0x36` | uint32 | tile height | high |
| `0x3a` | uint32 | thumbnail width | high |
| `0x3e` | uint32 | thumbnail height | high |
| `0x48` | float32 | pixel-size or scale-like value | medium |
| `0x4c` | float64 | pixel-size or scale-like value | medium |
| `0x54` | uint32 | scan magnification, observed `40` | high |
| `0x58` | uint32 | metadata offset, observed `6964` | high |

## Metadata JSON Contract

OpenSqray currently emits SDPC metadata as
`schema_version="opensqray.sdpc.metadata.v1"`.

The v1 output keeps three categories distinct:

* **Stable structural fields**: `version`, `file_size`, `stored_file_size`,
  `file_size_matches_header`, `header_size`, `level_count`, `dimensions`,
  `tile_size`, `thumbnail_size`, `scan_magnification`, and `metadata_offset`.
* **Parsed metadata strings**: `metadata.device_id`, `metadata.acquired_at`,
  `metadata.scanner_model`, `metadata.objective`, and
  `metadata.embedded_strings`.
* **Research diagnostics**: `experimental`, `jpeg_streams`,
  `associated_images`, `tile_index`, `field_confidence`, and
  `validation.warnings`.

`field_confidence` is part of the output so downstream users can avoid treating
research diagnostics as formal format guarantees:

| Confidence | Meaning |
|---|---|
| `high` | Stable across current inspected samples and suitable for normal metadata use. |
| `medium` | Useful parsed metadata string, but classification is heuristic. |
| `experimental` | Exposed for format research and subject to revision. |
| `diagnostic` | Runtime or scanning aid, not a complete format model. |

Validation warnings are non-fatal. For example, a stored header file-size
mismatch is reported with `code="file_size_mismatch"` while parsing continues.

## Local Smoke Validation

The ignored local `data/` directory can be checked with:

```bash
python3 tools/validate_local_samples.py --compact
```

The M1 smoke check validated two local SDPC samples against the v1 metadata
contract without committing sample data. Both samples reported positive
dimensions, positive level counts, expected metadata keys, JPEG record previews,
and no validation warnings.

## Associated Image Candidates

M2 adds conservative embedded JPEG record parsing:

* A marker hit is treated as a JPEG record only when it has a parseable JPEG SOF
  size and an EOI marker.
* False positives such as `ff d8 ff` byte sequences inside compressed payloads
  are ignored.
* Leading JPEG records whose dimensions do not match the tile size are exposed
  under `associated_images.records`.
* Candidate role names such as `label_candidate` and `macro_candidate` are
  heuristic. They should not be described as confirmed SDPC directory roles
  until the underlying directory/index records are mapped.

The current local samples both expose two leading non-tile JPEG candidates. The
larger candidate is named `macro_candidate`; the other is named
`label_candidate`. No local sample has yet confirmed a JPEG stream whose encoded
dimensions exactly match the header thumbnail dimensions.

## Tile Grid Candidates

M3 adds a conservative tile-grid candidate model:

* Expected pyramid grids are inferred from level-0 dimensions, tile size, and
  level count using power-of-two downsampling.
* Tile candidates are valid JPEG records whose encoded dimensions match the
  header tile size.
* Tile coordinates are assigned row-major within each inferred level.
* Missing tiles are reported only when the JPEG scan is complete and the record
  preview is not truncated.
* Edge tile `valid_size` records the in-slide region covered by a tile; a tile
  can be marked `padded=true` when the encoded tile size is larger than the
  valid edge region.

This is still a candidate reconstruction. The formal SDPC tile index table has
not yet been located, so downstream code should treat `tile_index` as
experimental rather than a stable pixel-read contract.

## Slide Facade Boundaries

M4 adds `SDPCSlide`, an OpenSlide-like facade for metadata and raw JPEG
candidate byte access. The facade exposes:

* level-0 `dimensions`
* inferred `level_count`, `level_dimensions`, and `level_downsamples`
* string `properties` derived from parsed SDPC metadata
* associated-image candidate records keyed by heuristic names
* raw JPEG bytes for associated-image candidates and tile candidates present in
  the current parser preview

`SDPCSlide` does not claim reliable region reads. `read_region()` intentionally
raises `NotImplementedError` until the formal SDPC tile-index table is mapped
and region assembly is validated.

## Optional Image Decoding

M5 adds a Pillow-backed optional image adapter. Core SDPC parsing, associated
image inspection, tile-index candidate inspection, and raw JPEG byte reads still
work with only the Python standard library.

When the `image` optional dependency is installed, `SDPCSlide` can decode:

* associated-image candidate JPEG records via `read_associated_image()`
* tile candidate JPEG records via `read_tile_image()` and
  `read_tile_image_by_sequence()`

Decoded tile images inherit the same limitations as `tile_index`: they are
heuristic candidate tiles from the current parser preview, not proof that a
formal SDPC tile directory has been mapped. `read_region()` remains unsupported.

## Current Boundaries

OpenSqray currently treats formal tile-index table parsing, confirmed
associated-image role classification, and region reads as experimental future
work. The parser exposes conservative diagnostics first so later behavior can be
validated rather than inferred too aggressively.
