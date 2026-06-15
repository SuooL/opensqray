# SDK Runtime Validation

OpenSqray SDK validation is stronger than a smoke test. A runtime is not
considered validated just because the service library can be loaded or one
region can be read.

## Validation Command

Run the practical validator against a real local SDPC file:

```bash
python3 tools/validate_sdk_runtime.py path/to/slide.sdpc \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --workers 4 \
  --patch-size 256 \
  --patch-count 16 \
  --repeat-count 2 \
  --output /tmp/opensqray-validation-full.json \
  --summary-output /tmp/opensqray-validation-summary.json
```

On Windows, pass the SDK `bin/` directory if you do not use `--sdk-dir`:

```powershell
python tools/validate_sdk_runtime.py C:\slides\sample.sdpc `
  --sdk-lib-dir C:\sqrayslide\bin `
  --workers 4
```

On macOS, the current vendor SDK may require native-library paths before Python
starts:

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib
export DYLD_LIBRARY_PATH="$OPENSQRAY_SDK_LIB_DIR:/path/to/libomp/lib:${DYLD_LIBRARY_PATH:-}"
python3 tools/validate_sdk_runtime.py path/to/slide.sdpc --workers 4
```

The command emits `opensqray.sdk.validation.v1` JSON and exits:

- `0` when all required checks pass
- `1` when the input file is missing
- `2` when runtime loading or validation fails

## What It Validates

The validator checks:

- runtime can open the real SDPC slide through `OpenSqraySlide`
- OpenSlide-like geometry is internally consistent
- required properties are present
- associated images can be decoded and hashed
- thumbnail respects the requested bounding box
- SDK tile JPEGs have valid JPEG markers and stable hashes
- sampled regions across the slide return images with expected sizes
- repeated serial reads produce identical image hashes
- parallel `read_regions(workers=...)` matches the serial baseline
- throughput is measured as regions/second for the sampled patch batch

The report includes SHA-256 hashes for image and tile outputs so two platforms
can be compared without committing slide data or image artifacts.

Use `--summary-output` for sanitized platform matrices and release notes. The
summary omits per-image hash lists and uses:

```text
opensqray.sdk.validation_summary.v1
```

## Platform Matrix

Each supported platform should run the same validator on the same public or
internal validation slide set:

| Platform | Runtime source | Required status | Current evidence |
| --- | --- | --- | --- |
| Windows x86_64 | SDK `bin/` or private runtime wheel | `status="passed"` | Not yet validated |
| Linux x86_64 | SDK `lib/` or private runtime wheel | `status="passed"` | Passed on Ubuntu with GitHub-synced `dev`, public `20220514_145829_0.sdpc`, no `LD_LIBRARY_PATH`, validator exit `0` |
| Linux arm64 | SDK `lib/` or private runtime wheel | `status="passed"` | Not yet validated |
| macOS Apple Silicon | SDK `lib/` or private runtime wheel | `status="passed"` | Passed locally with official SDK runtime and public `20220514_145829_0.sdpc` |
| macOS Intel | vendor-provided matching runtime | `status="passed"` when a runtime exists | Not yet validated; requires matching vendor runtime |

macOS Intel cannot be validated from an Apple Silicon-only SDK binary. It needs
a vendor-supported x86_64 or universal runtime.

## Pass Criteria

A platform runtime is considered practically validated only when:

- the validator exits `0`
- `status` is `passed`
- `errors` is empty
- repeated serial hashes match the baseline
- parallel hashes match the serial baseline
- tile JPEG records have valid JPEG markers
- the report records non-null `regions_per_second`

This does not prove full OpenSlide parity. It proves the current minimal
OpenSqray SDK wrapper can support real OpenSlide-like SDPC reads and patch
extraction on that platform.

## Suggested Validation Set

Use at least:

- the public `20220514_145829_0.sdpc` sample when locally available
- one large internal SDPC with many tiles
- one edge-case SDPC from a different scanner/software version

Do not commit full slide files or SDK binaries. Store full validation reports
outside the public repository, or attach sanitized summaries to internal release
notes. See [Validation Result Summaries](validation-results/README.md).
