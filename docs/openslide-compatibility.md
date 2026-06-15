# OpenSlide Compatibility Matrix

OpenSqray is OpenSlide-like for the common SDPC workflows needed by pathology
patch extraction and slide inspection. It is not a complete clone of every
OpenSlide Python behavior.

## Supported For SDPC

| OpenSlide-style capability | OpenSqray support |
| --- | --- |
| `open_slide(path)` | SDPC paths return `OpenSqraySlide`; non-SDPC paths delegate to OpenSlide |
| `detect_format(path)` | SDPC returns `sqray`; non-SDPC paths delegate to `openslide.OpenSlide.detect_format` when OpenSlide is available |
| `dimensions` | Supported through SDK backend |
| `level_count` | Supported through SDK backend |
| `level_dimensions` | Supported through SDK backend |
| `level_downsamples` | Supported, computed from level dimensions for OpenSlide-style semantics |
| `properties` | Supported core OpenSlide-style fields plus `opensqray.*` diagnostics |
| property name constants | Supported for common `PROPERTY_NAME_*` fields exposed by `OpenSqraySlide` |
| `associated_images` | Supported for SDK-provided `label`, `thumbnail`, and `macro` |
| `read_region(location, level, size)` | Supported with OpenSlide-style level-0 coordinates |
| `get_thumbnail(size)` | Supported |
| `get_best_level_for_downsample(downsample)` | Supported |
| context manager / `close()` | Supported |

## OpenSqray Extensions

| Capability | Purpose |
| --- | --- |
| `read_tile_jpeg_bytes(level=..., tile_x=..., tile_y=...)` | Raw SDK tile JPEG access |
| `RegionRequest` | Explicit patch request object |
| `read_regions(...)` | Ordered batch reads with bounded worker count |
| `iter_regions(...)` | Chunked streaming reads for large patch jobs |
| `iter_patch_requests(...)` | Simple grid patch request generation |
| `validate_sdk_runtime(...)` | Real runtime validation on SDPC files |

## Not Yet Implemented

| OpenSlide behavior | Current decision |
| --- | --- |
| Error-latching semantics | Not implemented; current methods raise normal Python exceptions |
| DeepZoom helpers | Not implemented; can be added as a separate adapter if needed |
| ICC profile parity | Not implemented; SDK color APIs need separate SDPC semantics first |
| Multi-channel / focal-plane APIs | Not implemented; not part of the minimal brightfield OpenSlide workflow |
| Native SDPC `read_region()` without SDK | Not implemented; native parser remains research/metadata only |

## Boundary

If your workflow needs SVS or other standard WSI formats, OpenSqray delegates to
`openslide.OpenSlide`. If your workflow needs practical SDPC pixel reads, use
`OpenSqraySlide` with a legally configured Sqray SDK runtime.
