"""OpenSlide-like SDPC slide facade.

The facade exposes stable metadata and raw JPEG candidate bytes. When the
optional Sqray SDK backend is explicitly enabled, it can also delegate tile and
region reads to the vendor runtime.
"""

from __future__ import annotations

from pathlib import Path

from .image_adapter import decode_jpeg_bytes, image_from_bgra_bytes
from .sdpc import (
    SDPC_METADATA_SCHEMA_VERSION,
    SDPCFormatError,
    SDPCInfo,
    read_sdpc,
    read_sdpc_byte_range,
)
from .sdk_backend import SqraySDKSlide


class SDPCSlide:
    """OpenSlide-like facade for SDPC metadata and candidate JPEG bytes.

    The default ``native`` backend exposes heuristic tile candidates. The
    optional ``sdk`` backend delegates tile/region reads to a locally configured
    Sqray SDK runtime.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        scan_jpegs: bool = False,
        jpeg_preview_limit: int = 50,
        backend: str = "native",
        sdk_dir: str | Path | None = None,
        sdk_lib_dir: str | Path | None = None,
    ) -> None:
        if jpeg_preview_limit <= 0:
            raise ValueError("jpeg_preview_limit must be positive")
        if backend not in {"native", "sdk"}:
            raise ValueError("backend must be 'native' or 'sdk'")

        self._path = Path(path)
        self._backend_name = backend
        self._info = read_sdpc(
            self._path,
            scan_jpegs=scan_jpegs,
            jpeg_preview_limit=jpeg_preview_limit,
        )
        self._sdk_slide = (
            SqraySDKSlide(self._path, sdk_dir=sdk_dir, lib_dir=sdk_lib_dir)
            if backend == "sdk"
            else None
        )
        self._closed = False

    def close(self) -> None:
        """Mark this facade closed."""

        if self._sdk_slide is not None:
            self._sdk_slide.close()
        self._closed = True

    def __enter__(self) -> SDPCSlide:
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def path(self) -> str:
        """Return the SDPC file path."""

        self._require_open()
        return str(self._path)

    @property
    def info(self) -> SDPCInfo:
        """Return the parsed SDPC metadata object."""

        self._require_open()
        return self._info

    @property
    def dimensions(self) -> tuple[int, int]:
        """Return level-0 dimensions as ``(width, height)``."""

        self._require_open()
        return self._info.dimensions

    @property
    def level_count(self) -> int:
        """Return the number of inferred pyramid levels."""

        self._require_open()
        return self._info.level_count

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        """Return inferred level dimensions as ``(width, height)`` tuples."""

        self._require_open()
        return tuple(_level_dimensions(self._info))

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        """Return power-of-two downsample factors for inferred levels."""

        self._require_open()
        return tuple(float(2 ** level) for level in range(self.level_count))

    @property
    def properties(self) -> dict[str, str]:
        """Return OpenSlide-style string properties for stable SDPC metadata."""

        self._require_open()
        properties = _slide_properties(self._info)
        properties["opensqray.backend"] = self._backend_name
        return properties

    @property
    def associated_images(self) -> dict[str, dict[str, object]]:
        """Return associated-image candidate records keyed by heuristic name."""

        self._require_open()
        return _associated_records_by_name(self._info)

    @property
    def tile_index(self) -> dict[str, object]:
        """Return the heuristic tile-index candidate model."""

        self._require_open()
        return dict(self._info.tile_index)

    def read_associated_image_bytes(self, name: str) -> bytes:
        """Return raw JPEG bytes for an associated-image candidate."""

        self._require_open()
        record = self.associated_images.get(name)
        if record is None:
            raise KeyError(f"unknown associated-image candidate: {name}")
        return self._read_record_bytes(record)

    def read_associated_image(self, name: str) -> object:
        """Decode and return an associated-image candidate with Pillow."""

        return decode_jpeg_bytes(self.read_associated_image_bytes(name))

    def read_tile_jpeg_bytes(self, *, level: int, tile_x: int, tile_y: int) -> bytes:
        """Return raw JPEG bytes for a tile coordinate."""

        self._require_open()
        if self._sdk_slide is not None:
            return self._sdk_slide.read_tile_jpeg_bytes(
                level=level,
                tile_x=tile_x,
                tile_y=tile_y,
            )

        for record in _tile_records(self._info):
            if (
                record.get("level") == level
                and record.get("tile_x") == tile_x
                and record.get("tile_y") == tile_y
            ):
                return self._read_record_bytes(record)

        raise KeyError(
            "tile JPEG candidate is not present in the current preview; "
            "increase jpeg_preview_limit or wait for formal SDPC tile-index "
            "mapping"
        )

    def read_tile_image(self, *, level: int, tile_x: int, tile_y: int) -> object:
        """Decode and return a tile candidate with Pillow."""

        return decode_jpeg_bytes(
            self.read_tile_jpeg_bytes(level=level, tile_x=tile_x, tile_y=tile_y)
        )

    def read_tile_jpeg_bytes_by_sequence(self, sequence_index: int) -> bytes:
        """Return raw JPEG bytes for a tile candidate by preview sequence."""

        self._require_open()
        for record in _tile_records(self._info):
            if record.get("sequence_index") == sequence_index:
                return self._read_record_bytes(record)

        raise KeyError(
            "tile JPEG candidate sequence is not present in the current preview; "
            "increase jpeg_preview_limit or wait for formal SDPC tile-index "
            "mapping"
        )

    def read_tile_image_by_sequence(self, sequence_index: int) -> object:
        """Decode and return a tile candidate by preview sequence with Pillow."""

        return decode_jpeg_bytes(self.read_tile_jpeg_bytes_by_sequence(sequence_index))

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> object:
        """Return an RGBA Pillow image for a region when SDK backend is active."""

        return image_from_bgra_bytes(
            self.read_region_bgra_bytes(location, level, size),
            size,
        )

    def read_region_bgra_bytes(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> bytes:
        """Return BGRA bytes for a region when SDK backend is active."""

        self._require_open()
        if self._sdk_slide is not None:
            return self._sdk_slide.read_region_bgra_bytes(
                location=_sdk_location_for_level(self._sdk_slide, location, level),
                level=level,
                size=size,
            )

        raise NotImplementedError(
            "SDPCSlide.read_region is not implemented yet; tile coordinates "
            "remain heuristic until the formal SDPC tile-index table is mapped"
        )

    def _read_record_bytes(self, record: dict[str, object]) -> bytes:
        return read_sdpc_byte_range(
            self._path,
            offset=_record_int(record, "offset"),
            length=_record_int(record, "length"),
        )

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("SDPCSlide is closed")


def _level_dimensions(info: SDPCInfo) -> list[tuple[int, int]]:
    dimensions: list[tuple[int, int]] = []
    for level in info.tile_index.get("levels", []):
        if not isinstance(level, dict):
            continue
        size = level.get("dimensions")
        if not isinstance(size, dict):
            continue
        width = size.get("width")
        height = size.get("height")
        if isinstance(width, int) and isinstance(height, int):
            dimensions.append((width, height))

    if len(dimensions) == info.level_count:
        return dimensions

    return [
        (
            max(1, _ceil_div(info.dimensions[0], 2 ** level)),
            max(1, _ceil_div(info.dimensions[1], 2 ** level)),
        )
        for level in range(info.level_count)
    ]


def _sdk_location_for_level(
    sdk_slide: SqraySDKSlide,
    location: tuple[int, int],
    level: int,
) -> tuple[int, int]:
    if level < 0 or level >= sdk_slide.level_count:
        raise ValueError(f"level out of range: {level}")
    downsample = _sdk_level_downsamples(sdk_slide)[level]
    return int(location[0] / downsample), int(location[1] / downsample)


def _sdk_level_downsamples(sdk_slide: SqraySDKSlide) -> tuple[float, ...]:
    level_dimensions = tuple(
        sdk_slide.level_size(level)
        for level in range(sdk_slide.level_count)
    )
    base_width, base_height = level_dimensions[0]
    downsamples = []
    for width, height in level_dimensions:
        width_downsample = base_width / width if width else 1.0
        height_downsample = base_height / height if height else 1.0
        downsamples.append(max(width_downsample, height_downsample))
    return tuple(downsamples)


def _slide_properties(info: SDPCInfo) -> dict[str, str]:
    properties = {
        "opensqray.format": "sdpc",
        "opensqray.schema_version": SDPC_METADATA_SCHEMA_VERSION,
        "opensqray.sdpc.version": info.version,
        "opensqray.sdpc.level_count": str(info.level_count),
        "opensqray.sdpc.dimensions": _format_size(info.dimensions),
        "opensqray.sdpc.tile_size": _format_size(info.tile_size),
        "opensqray.sdpc.thumbnail_size": _format_size(info.thumbnail_size),
        "opensqray.sdpc.scan_magnification": (
            "" if info.scan_magnification is None else str(info.scan_magnification)
        ),
        "opensqray.sdpc.tile_index.status": str(info.tile_index.get("status")),
        "opensqray.sdpc.tile_index.confidence": str(
            info.tile_index.get("confidence")
        ),
    }

    for key in ("device_id", "acquired_at", "scanner_model", "objective"):
        value = info.metadata.get(key)
        if value is not None:
            properties[f"opensqray.sdpc.metadata.{key}"] = str(value)

    return properties


def _associated_records_by_name(info: SDPCInfo) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for record in info.associated_images.get("records", []):
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if isinstance(name, str):
            records[name] = dict(record)
    return records


def _tile_records(info: SDPCInfo) -> list[dict[str, object]]:
    return [
        dict(record)
        for record in info.tile_index.get("tiles_preview", [])
        if isinstance(record, dict)
    ]


def _record_int(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if type(value) is not int:
        raise SDPCFormatError(f"SDPC record is missing integer field: {key}")
    if value < 0:
        raise SDPCFormatError(f"SDPC record has negative field: {key}")
    return value


def _format_size(size: tuple[int, int]) -> str:
    return f"{size[0]}x{size[1]}"


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor
