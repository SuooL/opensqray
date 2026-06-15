"""Check a private OpenSqray SDK runtime package layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opensqray.runtime_package import check_runtime_package_layout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a private Sqray SDK runtime package layout."
    )
    parser.add_argument("root", type=Path, help="runtime package root directory")
    parser.add_argument(
        "--platform-tag",
        default=None,
        help="platform tag such as linux-x86_64, macos-arm64, windows-x86_64",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    payload = check_runtime_package_layout(
        args.root,
        platform_tag=args.platform_tag,
    )
    indent = None if args.compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
