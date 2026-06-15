"""Run practical validation against a configured Sqray SDK runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opensqray.image_adapter import ImageDecodeUnavailable  # noqa: E402
from opensqray.sdk_backend import SqraySDKError, SqraySDKUnavailable  # noqa: E402
from opensqray.sdk_validation import (  # noqa: E402
    OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
    summarize_sdk_validation,
    validate_sdk_runtime,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a real Sqray SDK runtime with metadata, tile, region, "
            "batch consistency, and throughput checks."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=Path("data/20220514_145829_0.sdpc"),
        type=Path,
        help="local SDPC file to validate",
    )
    parser.add_argument("--sdk-dir", type=Path, default=None)
    parser.add_argument("--sdk-lib-dir", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patch-size", type=int, default=128)
    parser.add_argument("--patch-count", type=int, default=8)
    parser.add_argument("--repeat-count", type=int, default=2)
    parser.add_argument(
        "--thumbnail-size",
        type=_parse_size,
        default=(256, 256),
        help="thumbnail validation bounding box as WIDTHxHEIGHT",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional path to also write the JSON validation report",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="optional path to write a sanitized validation summary",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    if not args.path.exists():
        payload = _failure_payload(args.path, f"file not found: {args.path}")
        _emit(
            payload,
            compact=args.compact,
            output=args.output,
            summary_output=args.summary_output,
        )
        return 1

    try:
        payload = validate_sdk_runtime(
            args.path,
            sdk_dir=args.sdk_dir,
            sdk_lib_dir=args.sdk_lib_dir,
            workers=args.workers,
            patch_size=args.patch_size,
            patch_count=args.patch_count,
            repeat_count=args.repeat_count,
            thumbnail_size=args.thumbnail_size,
        )
    except (
        ImageDecodeUnavailable,
        OSError,
        SqraySDKError,
        SqraySDKUnavailable,
        ValueError,
    ) as exc:
        payload = _failure_payload(args.path, str(exc))
        _emit(
            payload,
            compact=args.compact,
            output=args.output,
            summary_output=args.summary_output,
        )
        return 2

    _emit(
        payload,
        compact=args.compact,
        output=args.output,
        summary_output=args.summary_output,
    )
    return 0 if payload["status"] == "passed" else 2


def _parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("thumbnail size must be positive")
    return width, height


def _failure_payload(path: Path, error: str) -> dict[str, Any]:
    return {
        "schema_version": OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
        "status": "failed",
        "path": str(path),
        "errors": [error],
        "warnings": [],
        "checks": {},
    }


def _emit(
    payload: dict[str, Any],
    *,
    compact: bool,
    output: Path | None,
    summary_output: Path | None,
) -> None:
    indent = None if compact else 2
    text = json.dumps(payload, indent=indent, sort_keys=True)
    print(text)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary = summarize_sdk_validation(payload)
        summary_text = json.dumps(summary, indent=indent, sort_keys=True)
        summary_output.write_text(summary_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
