# SDPC Format Notes

These notes are based on local binary inspection of SDPC samples and are safe for public documentation. They do not copy proprietary SDK implementation code.

## Confirmed Observations

Observed SDPC signatures:

* `SQ1.1.9.0430`
* `SQ1.0.0.0620`

Both inspected files contain embedded JPEG streams identifiable by `ff d8 ff` markers. The first JPEG marker was found at byte offset `7855` in both local samples.

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
  `field_confidence`, and `validation.warnings`.

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
dimensions, positive level counts, expected metadata keys, JPEG marker previews,
and no validation warnings.

## Current Boundaries

OpenSqray currently treats tile-index parsing, associated image classification, and region reads as experimental future work. The parser exposes conservative diagnostics first so later behavior can be validated rather than inferred too aggressively.
