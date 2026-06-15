"""Benchmark SDK-backed OpenSqray patch reads on a real SDPC slide."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opensqray import OpenSqraySlide, iter_patch_requests, read_regions  # noqa: E402
from opensqray.image_adapter import ImageDecodeUnavailable  # noqa: E402
from opensqray.sdk_backend import SqraySDKError, SqraySDKUnavailable  # noqa: E402


BENCHMARK_SCHEMA_VERSION = "opensqray.patch_benchmark.v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark SDK-backed SDPC patch reads."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--sdk-dir", type=Path, default=None)
    parser.add_argument("--sdk-lib-dir", type=Path, default=None)
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--stride", type=int, default=None)
    parser.add_argument("--count", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=32)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    try:
        payload = benchmark_patch_reads(
            args.path,
            sdk_dir=args.sdk_dir,
            sdk_lib_dir=args.sdk_lib_dir,
            level=args.level,
            patch_size=args.patch_size,
            stride=args.stride,
            count=args.count,
            workers=args.workers,
            chunk_size=args.chunk_size,
        )
    except (
        ImageDecodeUnavailable,
        OSError,
        SqraySDKError,
        SqraySDKUnavailable,
        ValueError,
    ) as exc:
        payload = {
            "schema_version": BENCHMARK_SCHEMA_VERSION,
            "status": "failed",
            "path": str(args.path),
            "errors": [str(exc)],
        }
        _print_json(payload, compact=args.compact)
        return 2

    _print_json(payload, compact=args.compact)
    return 0 if payload["status"] == "passed" else 2


def benchmark_patch_reads(
    path: str | Path,
    *,
    sdk_dir: str | Path | None = None,
    sdk_lib_dir: str | Path | None = None,
    level: int = 0,
    patch_size: int = 256,
    stride: int | None = None,
    count: int = 128,
    workers: int = 4,
    chunk_size: int = 32,
) -> dict[str, Any]:
    """Benchmark a bounded number of region reads and return JSON-safe stats."""

    if patch_size <= 0:
        raise ValueError("patch_size must be positive")
    if stride is not None and stride <= 0:
        raise ValueError("stride must be positive")
    if count <= 0:
        raise ValueError("count must be positive")
    if workers <= 0:
        raise ValueError("workers must be positive")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    slide_path = Path(path)
    if not slide_path.exists():
        raise FileNotFoundError(f"file not found: {slide_path}")

    with OpenSqraySlide(
        slide_path,
        sdk_dir=sdk_dir,
        sdk_lib_dir=sdk_lib_dir,
    ) as slide:
        dimensions = slide.dimensions

    requests = []
    for request in iter_patch_requests(
        dimensions,
        patch_size,
        stride=stride if stride is not None else patch_size,
        level=level,
    ):
        requests.append(request)
        if len(requests) >= count:
            break

    chunk_seconds: list[float] = []
    patch_count = 0
    started_at = time.perf_counter()
    for chunk in _chunks(requests, chunk_size):
        chunk_started_at = time.perf_counter()
        images = read_regions(
            slide_path,
            chunk,
            workers=workers,
            sdk_dir=sdk_dir,
            sdk_lib_dir=sdk_lib_dir,
        )
        for image in images:
            load = getattr(image, "load", None)
            if callable(load):
                load()
        chunk_seconds.append(time.perf_counter() - chunk_started_at)
        patch_count += len(images)
    elapsed = time.perf_counter() - started_at

    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "passed",
        "path": str(slide_path),
        "configuration": {
            "level": level,
            "patch_size": patch_size,
            "stride": stride if stride is not None else patch_size,
            "requested_count": count,
            "workers": workers,
            "chunk_size": chunk_size,
        },
        "slide": {
            "dimensions": {"width": dimensions[0], "height": dimensions[1]},
        },
        "results": {
            "patch_count": patch_count,
            "chunk_count": len(chunk_seconds),
            "seconds": round(elapsed, 6),
            "patches_per_second": (
                round(patch_count / elapsed, 3) if elapsed > 0 else None
            ),
            "median_chunk_seconds": _rounded_median(chunk_seconds),
            "p95_chunk_seconds": _rounded_quantile(chunk_seconds, 0.95),
        },
        "errors": [],
    }


def _chunks(values: list[object], chunk_size: int) -> list[list[object]]:
    return [
        values[index:index + chunk_size]
        for index in range(0, len(values), chunk_size)
    ]


def _rounded_median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 6)


def _rounded_quantile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
    return round(ordered[index], 6)


def _print_json(payload: dict[str, Any], *, compact: bool) -> None:
    indent = None if compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
