"""Validate ignored local SDPC samples against the public metadata contract."""

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

from opensqray.sdpc import (  # noqa: E402
    SDPC_METADATA_SCHEMA_VERSION,
    SDPCFormatError,
    read_sdpc,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate local ignored SDPC samples without committing or copying them."
        )
    )
    parser.add_argument(
        "sample_dir",
        nargs="?",
        default="data",
        type=Path,
        help="directory containing local *.sdpc samples",
    )
    parser.add_argument(
        "--scan-jpegs",
        action="store_true",
        help="scan full files for valid embedded JPEG record counts",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )
    parser.add_argument(
        "--require-samples",
        action="store_true",
        help="exit nonzero when no local samples are present",
    )
    args = parser.parse_args(argv)

    sample_dir = args.sample_dir
    paths = sorted(sample_dir.glob("*.sdpc")) if sample_dir.exists() else []
    result: dict[str, Any] = {
        "schema_version": SDPC_METADATA_SCHEMA_VERSION,
        "sample_dir": str(sample_dir),
        "sample_count": len(paths),
        "samples": [],
        "errors": [],
    }

    if not paths:
        result["message"] = "No local SDPC samples found."
        _print_json(result, compact=args.compact)
        return 1 if args.require_samples else 0

    for path in paths:
        try:
            payload = read_sdpc(path, scan_jpegs=args.scan_jpegs).to_dict()
        except (OSError, SDPCFormatError) as exc:
            result["errors"].append({"path": str(path), "error": str(exc)})
            continue

        sample = _summarize_payload(payload)
        result["samples"].append(sample)
        for error in _contract_errors(payload):
            result["errors"].append({"path": str(path), "error": error})

    _print_json(result, compact=args.compact)
    return 0 if not result["errors"] else 2


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload["metadata"]
    return {
        "path": payload["path"],
        "version": payload["version"],
        "file_size": payload["file_size"],
        "file_size_matches_header": payload["file_size_matches_header"],
        "level_count": payload["level_count"],
        "dimensions": payload["dimensions"],
        "tile_size": payload["tile_size"],
        "thumbnail_size": payload["thumbnail_size"],
        "scan_magnification": payload["scan_magnification"],
        "metadata_keys_present": [
            key
            for key in ("device_id", "acquired_at", "scanner_model", "objective")
            if metadata.get(key)
        ],
        "jpeg_streams": payload["jpeg_streams"],
        "associated_images": {
            "count": payload["associated_images"]["count"],
            "names": [
                record["name"]
                for record in payload["associated_images"]["records"]
            ],
        },
        "tile_index": {
            "status": payload["tile_index"]["status"],
            "preview_tile_count": len(payload["tile_index"]["tiles_preview"]),
            "preview_limited": payload["tile_index"]["preview_limited"],
        },
        "warnings": payload["validation"]["warnings"],
    }


def _contract_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if payload.get("format") != "sdpc":
        errors.append("format must be sdpc")
    if payload.get("schema_version") != SDPC_METADATA_SCHEMA_VERSION:
        errors.append("unexpected schema_version")
    if payload.get("level_count", 0) <= 0:
        errors.append("level_count must be positive")

    for field in ("dimensions", "tile_size", "thumbnail_size"):
        size = payload.get(field, {})
        if size.get("width", 0) <= 0 or size.get("height", 0) <= 0:
            errors.append(f"{field} width and height must be positive")

    tile_index = payload.get("tile_index", {})
    if tile_index.get("status") not in {"candidate", "unavailable"}:
        errors.append("tile_index.status must be candidate or unavailable")

    return errors


def _print_json(payload: dict[str, Any], *, compact: bool) -> None:
    indent = None if compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
