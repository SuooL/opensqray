"""Command-line interface for OpenSqray."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .openslide_adapter import OpenSlideUnavailable, inspect_with_openslide
from .sdpc import (
    SDPCFormatError,
    extract_sdpc_associated_images,
    is_sdpc,
    read_sdpc,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return _inspect(args)
    if args.command == "associated":
        return _associated(args)
    if args.command == "extract-associated":
        return _extract_associated(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opensqray",
        description="Inspect whole-slide image metadata.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect a slide")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument(
        "--scan-jpegs",
        action="store_true",
        help="scan the full SDPC file for valid embedded JPEG records",
    )
    inspect_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    associated_parser = subparsers.add_parser(
        "associated",
        help="list SDPC associated image candidates",
    )
    associated_parser.add_argument("path", type=Path)
    associated_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    extract_parser = subparsers.add_parser(
        "extract-associated",
        help="extract SDPC associated image JPEG candidates",
    )
    extract_parser.add_argument("path", type=Path)
    extract_parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="directory for extracted JPEG candidates",
    )
    extract_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing extracted files",
    )
    extract_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    return parser


def _inspect(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1

    try:
        if is_sdpc(path):
            payload = read_sdpc(path, scan_jpegs=args.scan_jpegs).to_dict()
        else:
            payload = inspect_with_openslide(path)
    except (SDPCFormatError, OpenSlideUnavailable, OSError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    _print_json(payload, compact=args.compact)
    return 0


def _associated(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print(
            "opensqray: associated image inspection is only supported for SDPC",
            file=sys.stderr,
        )
        return 2

    try:
        payload = read_sdpc(path).to_dict()["associated_images"]
    except (SDPCFormatError, OSError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    _print_json(payload, compact=args.compact)
    return 0


def _extract_associated(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print(
            "opensqray: associated image extraction is only supported for SDPC",
            file=sys.stderr,
        )
        return 2

    try:
        extracted = extract_sdpc_associated_images(
            path,
            args.output_dir,
            overwrite=args.overwrite,
        )
    except (SDPCFormatError, OSError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    payload = {
        "format": "sdpc",
        "path": str(path),
        "output_dir": str(args.output_dir),
        "extracted_count": len(extracted),
        "extracted": extracted,
    }
    _print_json(payload, compact=args.compact)
    return 0


def _print_json(payload: dict[str, object], *, compact: bool) -> None:
    indent = None if compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
