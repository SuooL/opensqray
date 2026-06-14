"""Command-line interface for OpenSqray."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .index_research import scan_sdpc_index_research
from .openslide_adapter import OpenSlideUnavailable, inspect_with_openslide
from .sdpc import (
    SDPCFormatError,
    extract_sdpc_associated_images,
    is_sdpc,
    read_sdpc,
)
from .sdk_backend import (
    SqraySDKError,
    SqraySDKUnavailable,
    inspect_sqray_sdk_slide,
)
from .slide import SDPCSlide


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return _inspect(args)
    if args.command == "associated":
        return _associated(args)
    if args.command == "extract-associated":
        return _extract_associated(args)
    if args.command == "tile-index":
        return _tile_index(args)
    if args.command == "index-research":
        return _index_research(args)
    if args.command == "sdk-info":
        return _sdk_info(args)
    if args.command == "read-tile":
        return _read_tile(args)

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

    tile_parser = subparsers.add_parser(
        "tile-index",
        help="inspect SDPC tile-grid candidates",
    )
    tile_parser.add_argument("path", type=Path)
    tile_parser.add_argument(
        "--scan-jpegs",
        action="store_true",
        help="scan the full SDPC file for valid embedded JPEG record counts",
    )
    tile_parser.add_argument(
        "--preview-limit",
        type=int,
        default=50,
        help="maximum number of JPEG records to keep in the preview",
    )
    tile_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    research_parser = subparsers.add_parser(
        "index-research",
        help="search SDPC files for diagnostic index-table candidates",
    )
    research_parser.add_argument("path", type=Path)
    research_parser.add_argument(
        "--scan-jpegs",
        action="store_true",
        help="scan the full SDPC file for valid embedded JPEG record counts",
    )
    research_parser.add_argument(
        "--preview-limit",
        type=int,
        default=50,
        help="maximum number of JPEG records to keep in the preview",
    )
    research_parser.add_argument(
        "--max-window-bytes",
        type=int,
        default=2 * 1024 * 1024,
        help="maximum bytes to search in each non-JPEG window",
    )
    research_parser.add_argument(
        "--min-table-matches",
        type=int,
        default=2,
        help="minimum consecutive packed values required for a candidate",
    )
    research_parser.add_argument(
        "--context-bytes",
        type=int,
        default=16,
        help="bytes of hex context to include before and after each candidate",
    )
    research_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    sdk_info_parser = subparsers.add_parser(
        "sdk-info",
        help="inspect a slide through a locally configured Sqray SDK runtime",
    )
    sdk_info_parser.add_argument("path", type=Path)
    _add_sdk_options(sdk_info_parser)
    sdk_info_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )

    read_tile_parser = subparsers.add_parser(
        "read-tile",
        help="write one SDPC tile JPEG",
    )
    read_tile_parser.add_argument("path", type=Path)
    read_tile_parser.add_argument("--level", type=int, required=True)
    read_tile_parser.add_argument("--tile-x", type=int, required=True)
    read_tile_parser.add_argument("--tile-y", type=int, required=True)
    read_tile_parser.add_argument("--output", required=True, type=Path)
    read_tile_parser.add_argument(
        "--backend",
        choices=("native", "sdk"),
        default="native",
        help="tile read backend; sdk uses the optional Sqray SDK runtime",
    )
    read_tile_parser.add_argument(
        "--preview-limit",
        type=int,
        default=50,
        help="maximum JPEG preview records for the native backend",
    )
    read_tile_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite output if it exists",
    )
    read_tile_parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON",
    )
    _add_sdk_options(read_tile_parser)

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


def _tile_index(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print(
            "opensqray: tile index inspection is only supported for SDPC",
            file=sys.stderr,
        )
        return 2
    if args.preview_limit <= 0:
        print("opensqray: --preview-limit must be positive", file=sys.stderr)
        return 2

    try:
        payload = read_sdpc(
            path,
            scan_jpegs=args.scan_jpegs,
            jpeg_preview_limit=args.preview_limit,
        ).to_dict()["tile_index"]
    except (SDPCFormatError, OSError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    _print_json(payload, compact=args.compact)
    return 0


def _index_research(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print(
            "opensqray: index research is only supported for SDPC",
            file=sys.stderr,
        )
        return 2
    if args.preview_limit <= 0:
        print("opensqray: --preview-limit must be positive", file=sys.stderr)
        return 2
    if args.max_window_bytes <= 0:
        print("opensqray: --max-window-bytes must be positive", file=sys.stderr)
        return 2
    if args.min_table_matches <= 0:
        print("opensqray: --min-table-matches must be positive", file=sys.stderr)
        return 2
    if args.context_bytes < 0:
        print("opensqray: --context-bytes must be non-negative", file=sys.stderr)
        return 2

    try:
        payload = scan_sdpc_index_research(
            path,
            scan_jpegs=args.scan_jpegs,
            jpeg_preview_limit=args.preview_limit,
            max_window_bytes=args.max_window_bytes,
            min_table_matches=args.min_table_matches,
            context_bytes=args.context_bytes,
        )
    except (SDPCFormatError, OSError, ValueError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    _print_json(payload, compact=args.compact)
    return 0


def _sdk_info(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print("opensqray: Sqray SDK inspection is only supported for SDPC", file=sys.stderr)
        return 2

    try:
        payload = inspect_sqray_sdk_slide(
            path,
            sdk_dir=args.sdk_dir,
            lib_dir=args.sdk_lib_dir,
        )
    except (SqraySDKError, SqraySDKUnavailable, OSError) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    _print_json(payload, compact=args.compact)
    return 0


def _read_tile(args: argparse.Namespace) -> int:
    path = args.path
    if not path.exists():
        print(f"opensqray: file not found: {path}", file=sys.stderr)
        return 1
    if not is_sdpc(path):
        print("opensqray: tile reads are only supported for SDPC", file=sys.stderr)
        return 2
    if args.preview_limit <= 0:
        print("opensqray: --preview-limit must be positive", file=sys.stderr)
        return 2

    try:
        with SDPCSlide(
            path,
            jpeg_preview_limit=args.preview_limit,
            backend=args.backend,
            sdk_dir=args.sdk_dir,
            sdk_lib_dir=args.sdk_lib_dir,
        ) as slide:
            jpeg_bytes = slide.read_tile_jpeg_bytes(
                level=args.level,
                tile_x=args.tile_x,
                tile_y=args.tile_y,
            )
    except (
        KeyError,
        SDPCFormatError,
        SqraySDKError,
        SqraySDKUnavailable,
        OSError,
        ValueError,
    ) as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    try:
        _write_output_bytes(args.output, jpeg_bytes, overwrite=args.overwrite)
    except OSError as exc:
        print(f"opensqray: {exc}", file=sys.stderr)
        return 2

    payload = {
        "format": "sdpc",
        "path": str(path),
        "backend": args.backend,
        "level": args.level,
        "tile_x": args.tile_x,
        "tile_y": args.tile_y,
        "output": str(args.output),
        "byte_length": len(jpeg_bytes),
        "content_type": "image/jpeg",
    }
    _print_json(payload, compact=args.compact)
    return 0


def _print_json(payload: dict[str, object], *, compact: bool) -> None:
    indent = None if compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))


def _add_sdk_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sdk-dir",
        type=Path,
        default=None,
        help="Sqray SDK root containing lib/; overrides OPENSQRAY_SDK_DIR",
    )
    parser.add_argument(
        "--sdk-lib-dir",
        type=Path,
        default=None,
        help="Sqray SDK library directory; overrides OPENSQRAY_SDK_LIB_DIR",
    )


def _write_output_bytes(path: Path, data: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


if __name__ == "__main__":
    raise SystemExit(main())
