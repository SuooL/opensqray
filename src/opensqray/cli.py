"""Command-line interface for OpenSqray."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .openslide_adapter import OpenSlideUnavailable, inspect_with_openslide
from .sdpc import SDPCFormatError, is_sdpc, read_sdpc


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return _inspect(args)

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
        help="scan the full SDPC file for embedded JPEG markers",
    )
    inspect_parser.add_argument(
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

    indent = None if args.compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

