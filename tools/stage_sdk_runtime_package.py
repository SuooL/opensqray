"""Stage a private OpenSqray SDK runtime package layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opensqray.runtime_package import stage_runtime_package_layout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage selected Sqray SDK runtime libraries into the private "
            "OpenSqray runtime package layout."
        )
    )
    parser.add_argument(
        "source_lib_dir",
        type=Path,
        help="SDK lib/ or bin/ directory containing the service library",
    )
    parser.add_argument("output_root", type=Path, help="runtime package root")
    parser.add_argument(
        "--platform-tag",
        default=None,
        help="platform tag such as linux-x86_64, macos-arm64, windows-x86_64",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing staged files and manifest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the staging plan without copying files",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    payload = stage_runtime_package_layout(
        args.source_lib_dir,
        args.output_root,
        platform_tag=args.platform_tag,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    indent = None if args.compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
