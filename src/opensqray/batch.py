"""Batch and patch helpers for SDK-backed SDPC region reads."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import islice
import os
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from .compat import OpenSqraySlide


@dataclass(frozen=True)
class RegionRequest:
    """One OpenSlide-style region request.

    ``location`` is expressed in level-0 pixel coordinates, matching
    ``openslide.OpenSlide.read_region``. ``size`` is the returned pixel size at
    the requested ``level``.
    """

    location: tuple[int, int]
    level: int
    size: tuple[int, int]
    key: object | None = None


@dataclass(frozen=True)
class RegionResult:
    """One streamed region-read result."""

    request: RegionRequest
    image: object

    @property
    def key(self) -> object | None:
        """Return the original request key for downstream patch writers."""

        return self.request.key


RegionRequestLike = RegionRequest | tuple[tuple[int, int], int, tuple[int, int]]

SlideFactory = Callable[..., object]


def iter_patch_requests(
    dimensions: tuple[int, int],
    patch_size: tuple[int, int] | int,
    *,
    level: int = 0,
    stride: tuple[int, int] | int | None = None,
    origin: tuple[int, int] = (0, 0),
    include_partial: bool = False,
) -> Iterable[RegionRequest]:
    """Yield a grid of OpenSlide-style patch requests.

    The grid is defined in level-0 coordinates. For level-0 patch extraction,
    ``patch_size`` and ``stride`` are therefore direct pixel units. For
    downsampled levels, callers should pass a level-0 stride that matches their
    intended sampling density.
    """

    width, height = _positive_size(dimensions, "dimensions")
    patch_width, patch_height = _coerce_size(patch_size, "patch_size")
    stride_width, stride_height = _coerce_size(
        stride if stride is not None else patch_size,
        "stride",
    )
    origin_x, origin_y = origin
    if origin_x < 0 or origin_y < 0:
        raise ValueError("origin must be non-negative")
    if level < 0:
        raise ValueError("level must be non-negative")

    y = origin_y
    while y < height:
        if not include_partial and y + patch_height > height:
            break
        x = origin_x
        current_height = min(patch_height, height - y)
        while x < width:
            if not include_partial and x + patch_width > width:
                break
            current_width = min(patch_width, width - x)
            yield RegionRequest(
                location=(x, y),
                level=level,
                size=(current_width, current_height),
                key=(x, y),
            )
            x += stride_width
        y += stride_height


def read_regions(
    path: str | Path,
    requests: Iterable[RegionRequestLike],
    *,
    workers: int | None = 1,
    sdk_dir: str | Path | None = None,
    sdk_lib_dir: str | Path | None = None,
    slide_factory: SlideFactory | None = None,
) -> list[object]:
    """Read many SDPC regions while preserving request order.

    Parallel reads use one SDK slide handle per worker instead of sharing a
    handle across threads. This is the conservative default until the vendor SDK
    documents handle-level thread-safety guarantees.
    """

    normalized = [_coerce_request(request) for request in requests]
    _validate_workers(workers)
    if not normalized:
        return []

    worker_count = _worker_count(workers, len(normalized))
    factory = slide_factory or OpenSqraySlide
    if worker_count == 1:
        with factory(path, sdk_dir=sdk_dir, sdk_lib_dir=sdk_lib_dir) as slide:
            return [_read_one(slide, request) for request in normalized]

    missing = object()
    results: list[object] = [missing] * len(normalized)
    chunks = _split_indexed_requests(normalized, worker_count)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _read_chunk,
                path,
                chunk,
                factory,
                sdk_dir,
                sdk_lib_dir,
            )
            for chunk in chunks
        ]
        for future in futures:
            for index, image in future.result():
                results[index] = image

    if any(image is missing for image in results):
        raise RuntimeError("internal batch read error: missing region result")
    return results


def iter_regions(
    path: str | Path,
    requests: Iterable[RegionRequestLike],
    *,
    workers: int | None = 1,
    chunk_size: int = 64,
    sdk_dir: str | Path | None = None,
    sdk_lib_dir: str | Path | None = None,
    slide_factory: SlideFactory | None = None,
) -> Iterator[RegionResult]:
    """Yield region images chunk by chunk while preserving request order.

    This is the memory-bounded companion to ``read_regions()``. It does not
    materialize the full request stream or the full image result set at once,
    making it the preferred API for large patch extraction jobs.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    _validate_workers(workers)

    iterator = iter(requests)
    while True:
        chunk = [_coerce_request(item) for item in islice(iterator, chunk_size)]
        if not chunk:
            return
        images = read_regions(
            path,
            chunk,
            workers=workers,
            sdk_dir=sdk_dir,
            sdk_lib_dir=sdk_lib_dir,
            slide_factory=slide_factory,
        )
        for request, image in zip(chunk, images):
            yield RegionResult(request=request, image=image)


def recommended_worker_count(
    *,
    slide_count: int = 1,
    max_workers: int | None = None,
) -> int:
    """Return a conservative worker count for SDK-backed patch extraction."""

    cpu_count = os.cpu_count() or 1
    ceiling = max_workers if max_workers is not None else min(8, cpu_count)
    if ceiling <= 0:
        raise ValueError("max_workers must be positive")
    if slide_count <= 0:
        raise ValueError("slide_count must be positive")
    return max(1, min(ceiling, slide_count * 2, cpu_count))


def _read_chunk(
    path: str | Path,
    indexed_requests: Sequence[tuple[int, RegionRequest]],
    slide_factory: SlideFactory,
    sdk_dir: str | Path | None,
    sdk_lib_dir: str | Path | None,
) -> list[tuple[int, object]]:
    with slide_factory(path, sdk_dir=sdk_dir, sdk_lib_dir=sdk_lib_dir) as slide:
        return [
            (index, _read_one(slide, request))
            for index, request in indexed_requests
        ]


def _read_one(slide: object, request: RegionRequest) -> object:
    return slide.read_region(request.location, request.level, request.size)


def _split_indexed_requests(
    requests: Sequence[RegionRequest],
    worker_count: int,
) -> list[list[tuple[int, RegionRequest]]]:
    chunks: list[list[tuple[int, RegionRequest]]] = [
        [] for _ in range(worker_count)
    ]
    for index, request in enumerate(requests):
        chunks[index % worker_count].append((index, request))
    return [chunk for chunk in chunks if chunk]


def _worker_count(workers: int | None, request_count: int) -> int:
    _validate_workers(workers)
    if workers is None:
        workers = 1
    return min(workers, request_count)


def _validate_workers(workers: int | None) -> None:
    if workers is None:
        return
    if workers <= 0:
        raise ValueError("workers must be positive")


def _coerce_request(request: RegionRequestLike) -> RegionRequest:
    if isinstance(request, RegionRequest):
        _positive_size(request.size, "request size")
        if request.level < 0:
            raise ValueError("request level must be non-negative")
        location_x, location_y = request.location
        if location_x < 0 or location_y < 0:
            raise ValueError("request location must be non-negative")
        return request

    try:
        location, level, size = request
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "region requests must be RegionRequest objects or "
            "(location, level, size) tuples"
        ) from exc
    return _coerce_request(RegionRequest(location, int(level), size))


def _coerce_size(value: tuple[int, int] | int, name: str) -> tuple[int, int]:
    if isinstance(value, int):
        return _positive_size((value, value), name)
    return _positive_size(value, name)


def _positive_size(size: tuple[int, int], name: str) -> tuple[int, int]:
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive")
    return width, height
