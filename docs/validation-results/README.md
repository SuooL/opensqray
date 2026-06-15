# Validation Result Summaries

This directory is for sanitized validation summaries, not full slide data,
SDK binaries, or large image artifacts.

Do not commit:

- `data/*.sdpc` or other full slide files
- `sqrayslide_20251128_x64/` or any proprietary SDK runtime binaries
- full validator JSON reports when they include detailed hashes for every
  sampled image

Preferred workflow:

```bash
python3 tools/validate_sdk_runtime.py data/20220514_145829_0.sdpc \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --workers 4 \
  --patch-size 256 \
  --patch-count 16 \
  --output /tmp/opensqray-validation-full.json \
  --summary-output /tmp/opensqray-validation-summary.json
```

The summary uses:

```text
opensqray.sdk.validation_summary.v1
```

Record platform evidence in release notes or internal validation trackers with:

- platform and architecture
- Python version
- SDK runtime source
- SDPC sample set
- validator exit code
- `status`
- `error_count`
- `warning_count`
- `repeat_matches`
- `parallel_matches`
- `regions_per_second`

Source code for remote validation should be synchronized through GitHub
branches and PRs:

```bash
git fetch origin
git switch dev
git pull --ff-only origin dev
```

Keep local ignored validation assets on the target machine.
