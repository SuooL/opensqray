"""Validation helpers for real Sqray SDK runtime deployments."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path
import platform
import sys
import time
from typing import Any, Callable, Iterable

from .batch import RegionRequest, read_regions
from .compat import OpenSqraySlide
from .sdk_backend import (
    OPENSQRAY_SDK_DIR_ENV,
    OPENSQRAY_SDK_LIB_DIR_ENV,
    OPENSQRAY_SDK_RUNTIME_ROOT_ENV,
    OPENSQRAY_SDK_RUNTIME_PACKAGE_ENV,
)


OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION = "opensqray.sdk.validation.v1"

SlideFactory = Callable[..., object]


def validate_sdk_runtime(
    path: str | Path,
    *,
    sdk_dir: str | Path | None = None,
    sdk_lib_dir: str | Path | None = None,
    workers: int = 2,
    patch_size: int = 128,
    patch_count: int = 8,
    repeat_count: int = 2,
    thumbnail_size: tuple[int, int] = (256, 256),
    slide_factory: SlideFactory | None = None,
) -> dict[str, Any]:
    """Run practical SDK runtime validation on a real SDPC slide.

    This is deliberately stronger than a smoke test. It validates metadata,
    associated images, tile JPEGs, multiple regions, repeat-read consistency,
    serial-vs-parallel batch consistency, and basic throughput.
    """

    _validate_positive("workers", workers)
    _validate_positive("patch_size", patch_size)
    _validate_positive("patch_count", patch_count)
    _validate_positive("repeat_count", repeat_count)
    _validate_size("thumbnail_size", thumbnail_size)

    slide_path = Path(path)
    factory = slide_factory or OpenSqraySlide
    started_at = time.perf_counter()
    errors: list[str] = []
    warnings: list[str] = []

    payload: dict[str, Any] = {
        "schema_version": OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
        "status": "failed",
        "path": str(slide_path),
        "platform": _platform_payload(),
        "runtime": {
            "sdk_dir": str(sdk_dir) if sdk_dir is not None else None,
            "sdk_lib_dir": str(sdk_lib_dir) if sdk_lib_dir is not None else None,
            "env_keys": [
                OPENSQRAY_SDK_DIR_ENV,
                OPENSQRAY_SDK_LIB_DIR_ENV,
                OPENSQRAY_SDK_RUNTIME_ROOT_ENV,
                OPENSQRAY_SDK_RUNTIME_PACKAGE_ENV,
            ],
        },
        "configuration": {
            "workers": workers,
            "patch_size": patch_size,
            "patch_count": patch_count,
            "repeat_count": repeat_count,
            "thumbnail_size": _size_dict(thumbnail_size),
        },
        "checks": {},
        "errors": errors,
        "warnings": warnings,
    }

    with factory(slide_path, sdk_dir=sdk_dir, sdk_lib_dir=sdk_lib_dir) as slide:
        geometry = _validate_geometry(slide, errors)
        payload["checks"]["geometry"] = geometry
        payload["checks"]["properties"] = _validate_properties(slide, errors)
        payload["checks"]["associated_images"] = _validate_associated_images(
            slide,
            warnings,
        )
        payload["checks"]["thumbnail"] = _validate_thumbnail(
            slide,
            thumbnail_size,
            errors,
        )
        payload["checks"]["tile_jpegs"] = _validate_tile_jpegs(
            slide,
            geometry,
            errors,
            warnings,
        )

    requests = _sample_region_requests(
        geometry,
        patch_size=patch_size,
        patch_count=patch_count,
    )
    payload["checks"]["region_requests"] = [asdict(request) for request in requests]

    serial_summaries = _read_region_summaries(
        slide_path,
        requests,
        workers=1,
        sdk_dir=sdk_dir,
        sdk_lib_dir=sdk_lib_dir,
        slide_factory=factory,
    )
    payload["checks"]["serial_regions"] = {
        "count": len(serial_summaries),
        "images": serial_summaries,
    }

    repeat_summaries = []
    for repeat_index in range(1, repeat_count):
        summaries = _read_region_summaries(
            slide_path,
            requests,
            workers=1,
            sdk_dir=sdk_dir,
            sdk_lib_dir=sdk_lib_dir,
            slide_factory=factory,
        )
        repeat_summaries.append(
            _compare_region_summaries(
                serial_summaries,
                summaries,
                label=f"repeat_{repeat_index}",
            )
        )
    payload["checks"]["repeat_consistency"] = repeat_summaries
    for item in repeat_summaries:
        if not item["matches"]:
            errors.append(f"{item['label']} region hashes differ from baseline")

    timed_start = time.perf_counter()
    parallel_summaries = _read_region_summaries(
        slide_path,
        requests,
        workers=workers,
        sdk_dir=sdk_dir,
        sdk_lib_dir=sdk_lib_dir,
        slide_factory=factory,
    )
    timed_seconds = time.perf_counter() - timed_start
    parallel_compare = _compare_region_summaries(
        serial_summaries,
        parallel_summaries,
        label="parallel",
    )
    if not parallel_compare["matches"]:
        errors.append("parallel region hashes differ from serial baseline")

    payload["checks"]["parallel_regions"] = {
        "workers": workers,
        "count": len(parallel_summaries),
        "images": parallel_summaries,
        "consistency": parallel_compare,
    }
    payload["checks"]["performance"] = {
        "region_count": len(parallel_summaries),
        "seconds": round(timed_seconds, 6),
        "regions_per_second": (
            round(len(parallel_summaries) / timed_seconds, 3)
            if timed_seconds > 0
            else None
        ),
    }

    payload["duration_seconds"] = round(time.perf_counter() - started_at, 6)
    payload["status"] = "passed" if not errors else "failed"
    return payload


def summarize_sdk_validation(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized validation summary for release notes or matrices."""

    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}
    geometry = checks.get("geometry", {})
    if not isinstance(geometry, dict):
        geometry = {}
    associated = checks.get("associated_images", {})
    if not isinstance(associated, dict):
        associated = {}
    tile_jpegs = checks.get("tile_jpegs", {})
    if not isinstance(tile_jpegs, dict):
        tile_jpegs = {}
    serial_regions = checks.get("serial_regions", {})
    if not isinstance(serial_regions, dict):
        serial_regions = {}
    repeat_consistency = checks.get("repeat_consistency", [])
    if not isinstance(repeat_consistency, list):
        repeat_consistency = []
    parallel_regions = checks.get("parallel_regions", {})
    if not isinstance(parallel_regions, dict):
        parallel_regions = {}
    parallel_consistency = parallel_regions.get("consistency", {})
    if not isinstance(parallel_consistency, dict):
        parallel_consistency = {}
    performance = checks.get("performance", {})
    if not isinstance(performance, dict):
        performance = {}

    return {
        "schema_version": "opensqray.sdk.validation_summary.v1",
        "source_schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "platform": payload.get("platform", {}),
        "configuration": payload.get("configuration", {}),
        "error_count": len(payload.get("errors", [])),
        "warning_count": len(payload.get("warnings", [])),
        "dimensions": geometry.get("dimensions"),
        "level_count": geometry.get("level_count"),
        "associated_count": associated.get("count"),
        "tile_jpeg_count": tile_jpegs.get("count"),
        "region_count": serial_regions.get("count"),
        "repeat_matches": all(
            bool(item.get("matches"))
            for item in repeat_consistency
            if isinstance(item, dict)
        ),
        "parallel_matches": parallel_consistency.get("matches"),
        "regions_per_second": performance.get("regions_per_second"),
        "duration_seconds": payload.get("duration_seconds"),
    }


def _validate_geometry(slide: object, errors: list[str]) -> dict[str, Any]:
    dimensions = _tuple_size(getattr(slide, "dimensions"))
    level_count = int(getattr(slide, "level_count"))
    level_dimensions = tuple(
        _tuple_size(size) for size in getattr(slide, "level_dimensions")
    )
    level_downsamples = tuple(float(item) for item in getattr(slide, "level_downsamples"))

    if dimensions[0] <= 0 or dimensions[1] <= 0:
        errors.append("slide dimensions must be positive")
    if level_count <= 0:
        errors.append("level_count must be positive")
    if len(level_dimensions) != level_count:
        errors.append("level_dimensions length must equal level_count")
    if len(level_downsamples) != level_count:
        errors.append("level_downsamples length must equal level_count")
    if level_downsamples and level_downsamples[0] != 1.0:
        errors.append("level_downsamples[0] must be 1.0")
    if any(value <= 0 for value in level_downsamples):
        errors.append("level_downsamples must be positive")
    if any(
        level_downsamples[index] > level_downsamples[index + 1]
        for index in range(len(level_downsamples) - 1)
    ):
        errors.append("level_downsamples must be non-decreasing")

    return {
        "dimensions": _size_dict(dimensions),
        "dimensions_tuple": dimensions,
        "level_count": level_count,
        "level_dimensions": [_size_dict(size) for size in level_dimensions],
        "level_downsamples": list(level_downsamples),
    }


def _validate_properties(slide: object, errors: list[str]) -> dict[str, Any]:
    properties = dict(getattr(slide, "properties"))
    required = [
        "openslide.vendor",
        "opensqray.backend",
        "opensqray.format",
        "opensqray.schema_version",
    ]
    missing = [key for key in required if key not in properties]
    if missing:
        errors.append(f"missing required properties: {', '.join(missing)}")
    return {
        "required_keys": required,
        "missing_keys": missing,
        "sample": {key: properties.get(key) for key in required},
        "count": len(properties),
    }


def _validate_associated_images(
    slide: object,
    warnings: list[str],
) -> dict[str, Any]:
    associated = dict(getattr(slide, "associated_images"))
    if not associated:
        warnings.append("SDK returned no associated images")
    return {
        "count": len(associated),
        "images": {
            name: _image_summary(image)
            for name, image in sorted(associated.items())
        },
    }


def _validate_thumbnail(
    slide: object,
    thumbnail_size: tuple[int, int],
    errors: list[str],
) -> dict[str, Any]:
    image = slide.get_thumbnail(thumbnail_size)
    summary = _image_summary(image)
    width = summary["size"]["width"]
    height = summary["size"]["height"]
    if width > thumbnail_size[0] or height > thumbnail_size[1]:
        errors.append("thumbnail exceeds requested bounding box")
    return summary


def _validate_tile_jpegs(
    slide: object,
    geometry: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    tile_requests = _tile_requests(slide, int(geometry["level_count"]))
    records = []
    for request in tile_requests:
        try:
            data = slide.read_tile_jpeg_bytes(
                level=request["level"],
                tile_x=request["tile_x"],
                tile_y=request["tile_y"],
            )
        except Exception as exc:  # noqa: BLE001 - report validation failures.
            errors.append(f"tile JPEG read failed for {request}: {exc}")
            continue
        record = {
            **request,
            "byte_length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "valid_jpeg_markers": data.startswith(b"\xff\xd8")
            and data.endswith(b"\xff\xd9"),
        }
        if not record["valid_jpeg_markers"]:
            errors.append(f"tile JPEG has invalid markers for {request}")
        records.append(record)

    if not records:
        warnings.append("no tile JPEG records were validated")
    return {"count": len(records), "records": records}


def _tile_requests(slide: object, level_count: int) -> list[dict[str, int]]:
    requests = [{"level": 0, "tile_x": 0, "tile_y": 0}]
    sdk_slide = getattr(slide, "_sdk_slide", None)
    if sdk_slide is None or not hasattr(sdk_slide, "level_tile_count"):
        return requests

    for level in range(min(level_count, 2)):
        columns, rows = sdk_slide.level_tile_count(level)
        if columns > 1:
            requests.append({"level": level, "tile_x": 1, "tile_y": 0})
        if rows > 1:
            requests.append({"level": level, "tile_x": 0, "tile_y": 1})
    return _dedupe_tile_requests(requests)


def _sample_region_requests(
    geometry: dict[str, Any],
    *,
    patch_size: int,
    patch_count: int,
) -> list[RegionRequest]:
    level_count = int(geometry["level_count"])
    level_dimensions = [
        _tuple_size((item["width"], item["height"]))
        for item in geometry["level_dimensions"]
    ]
    level_downsamples = [float(item) for item in geometry["level_downsamples"]]
    levels = [0]
    if level_count > 1:
        levels.append(1)

    requests: list[RegionRequest] = []
    seen: set[tuple[int, int, int]] = set()
    for level in levels:
        level_width, level_height = level_dimensions[level]
        patch_width = min(patch_size, level_width)
        patch_height = min(patch_size, level_height)
        downsample = level_downsamples[level]
        for level_x, level_y in _level_positions(
            (level_width, level_height),
            (patch_width, patch_height),
        ):
            x = int(level_x * downsample)
            y = int(level_y * downsample)
            key = (level, x, y)
            if key in seen:
                continue
            seen.add(key)
            requests.append(
                RegionRequest(
                    location=(x, y),
                    level=level,
                    size=(patch_width, patch_height),
                    key=f"L{level}:{x},{y}",
                )
            )
            if len(requests) >= patch_count:
                return requests
    return requests


def _read_region_summaries(
    path: Path,
    requests: Iterable[RegionRequest],
    *,
    workers: int,
    sdk_dir: str | Path | None,
    sdk_lib_dir: str | Path | None,
    slide_factory: SlideFactory,
) -> list[dict[str, Any]]:
    images = read_regions(
        path,
        requests,
        workers=workers,
        sdk_dir=sdk_dir,
        sdk_lib_dir=sdk_lib_dir,
        slide_factory=slide_factory,
    )
    return [_image_summary(image) for image in images]


def _compare_region_summaries(
    baseline: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    *,
    label: str,
) -> dict[str, Any]:
    baseline_hashes = [item.get("sha256") for item in baseline]
    observed_hashes = [item.get("sha256") for item in observed]
    return {
        "label": label,
        "matches": baseline_hashes == observed_hashes,
        "baseline_hashes": baseline_hashes,
        "observed_hashes": observed_hashes,
    }


def _image_summary(image: object) -> dict[str, Any]:
    size = _tuple_size(getattr(image, "size"))
    mode = str(getattr(image, "mode", "unknown"))
    data = _image_bytes(image)
    summary: dict[str, Any] = {
        "size": _size_dict(size),
        "mode": mode,
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    extrema = _image_extrema(image)
    if extrema is not None:
        summary["extrema"] = extrema
    return summary


def _image_bytes(image: object) -> bytes:
    tobytes = getattr(image, "tobytes", None)
    if callable(tobytes):
        return bytes(tobytes())
    return repr(image).encode("utf-8")


def _image_extrema(image: object) -> object | None:
    getextrema = getattr(image, "getextrema", None)
    if not callable(getextrema):
        return None
    try:
        return getextrema()
    except Exception:  # noqa: BLE001 - extrema is diagnostic only.
        return None


def _dedupe_tile_requests(requests: list[dict[str, int]]) -> list[dict[str, int]]:
    deduped = []
    seen: set[tuple[int, int, int]] = set()
    for request in requests:
        key = (request["level"], request["tile_x"], request["tile_y"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(request)
    return deduped


def _level_positions(
    dimensions: tuple[int, int],
    patch_size: tuple[int, int],
) -> list[tuple[int, int]]:
    width, height = dimensions
    patch_width, patch_height = patch_size
    return [
        (0, 0),
        (
            _clamp_start(width // 2 - patch_width // 2, width, patch_width),
            _clamp_start(height // 2 - patch_height // 2, height, patch_height),
        ),
        (
            _clamp_start(width - patch_width, width, patch_width),
            _clamp_start(height - patch_height, height, patch_height),
        ),
        (
            _clamp_start(width // 3, width, patch_width),
            _clamp_start(height // 3, height, patch_height),
        ),
        (
            _clamp_start((2 * width) // 3, width, patch_width),
            _clamp_start((2 * height) // 3, height, patch_height),
        ),
    ]


def _clamp_start(start: int, extent: int, size: int) -> int:
    return max(0, min(start, max(0, extent - size)))


def _tuple_size(value: object) -> tuple[int, int]:
    width, height = value  # type: ignore[misc]
    return int(width), int(height)


def _size_dict(size: tuple[int, int]) -> dict[str, int]:
    return {"width": size[0], "height": size[1]}


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_size(name: str, value: tuple[int, int]) -> None:
    width, height = value
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive")


def _platform_payload() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }
