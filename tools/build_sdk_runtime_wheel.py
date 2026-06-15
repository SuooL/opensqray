"""Build a private OpenSqray SDK runtime wheel from a staged runtime root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opensqray.runtime_package import (  # noqa: E402
    DEFAULT_RUNTIME_WHEEL_PACKAGE_NAME,
    build_runtime_wheel,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a private platform wheel from a staged OpenSqray SDK "
            "runtime package root."
        )
    )
    parser.add_argument("runtime_root", type=Path, help="runtime package root")
    parser.add_argument("dist_dir", type=Path, help="output wheel directory")
    parser.add_argument(
        "--package-name",
        default=DEFAULT_RUNTIME_WHEEL_PACKAGE_NAME,
        help="importable runtime package name",
    )
    parser.add_argument(
        "--version",
        default="0.0.0+local",
        help="private runtime wheel version",
    )
    parser.add_argument(
        "--platform-tag",
        default=None,
        help="platform tag such as linux-x86_64, macos-arm64, windows-x86_64",
    )
    parser.add_argument(
        "--include-manifest",
        action="store_true",
        help="include the staging manifest even if it contains local paths",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite an existing wheel with the same name",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    payload = build_runtime_wheel(
        args.runtime_root,
        args.dist_dir,
        package_name=args.package_name,
        version=args.version,
        platform_tag=args.platform_tag,
        include_manifest=args.include_manifest,
        overwrite=args.overwrite,
    )
    indent = None if args.compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
