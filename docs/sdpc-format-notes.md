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

## Current Boundaries

OpenSqray currently treats tile-index parsing, associated image classification, and region reads as experimental future work. The parser exposes conservative diagnostics first so later behavior can be validated rather than inferred too aggressively.

