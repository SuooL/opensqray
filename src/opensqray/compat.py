"""OpenSlide-compatible facade for SDPC and OpenSlide-backed slides."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .image_adapter import decode_jpeg_bytes, image_from_bgra_bytes
from .openslide_adapter import OpenSlideUnavailable
from .sdpc import SDPC_METADATA_SCHEMA_VERSION, SDPCInfo, read_sdpc
from .sdk_backend import (
    SDK_ASSOCIATED_IMAGE_TYPES,
    SqraySDKError,
    SqraySDKSlide,
)


PROPERTY_NAME_VENDOR = "openslide.vendor"
PROPERTY_NAME_COMMENT = "openslide.comment"
PROPERTY_NAME_OBJECTIVE_POWER = "openslide.objective-power"
PROPERTY_NAME_MPP_X = "openslide.mpp-x"
PROPERTY_NAME_MPP_Y = "openslide.mpp-y"
PROPERTY_NAME_BOUNDS_X = "openslide.bounds-x"
PROPERTY_NAME_BOUNDS_Y = "openslide.bounds-y"
PROPERTY_NAME_BOUNDS_WIDTH = "openslide.bounds-width"
PROPERTY_NAME_BOUNDS_HEIGHT = "openslide.bounds-height"


class OpenSqraySlide:
    """OpenSlide-like SDPC slide object backed by the official Sqray SDK.

    This class is the practical compatibility layer for applications that need
    ``read_region()``, pyramid metadata, thumbnails, and associated images. It
    requires a locally configured Sqray SDK runtime and Pillow for image return
    objects, mirroring OpenSlide's PIL-oriented Python API.
    """

    def __init__(
        self,
        filename: str | Path,
        *,
        sdk_dir: str | Path | None = None,
        sdk_lib_dir: str | Path | None = None,
    ) -> None:
        self._path = Path(filename)
        self._info = read_sdpc(self._path)
        self._sdk_slide = SqraySDKSlide(
            self._path,
            sdk_dir=sdk_dir,
            lib_dir=sdk_lib_dir,
        )
        self._closed = False
        self._associated_images: Mapping[str, object] | None = None

    def close(self) -> None:
        """Close the underlying SDK slide handle."""

        if self._closed:
            return
        self._sdk_slide.close()
        self._closed = True

    def __enter__(self) -> OpenSqraySlide:
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def dimensions(self) -> tuple[int, int]:
        """Return level-0 dimensions as ``(width, height)``."""

        self._require_open()
        return self._sdk_slide.level_size(0)

    @property
    def level_count(self) -> int:
        """Return the number of pyramid levels."""

        self._require_open()
        return self._sdk_slide.level_count

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        """Return level dimensions as ``(width, height)`` tuples."""

        self._require_open()
        return tuple(
            self._sdk_slide.level_size(level)
            for level in range(self._sdk_slide.level_count)
        )

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        """Return OpenSlide-style downsample factors."""

        self._require_open()
        return _level_downsamples(self.level_dimensions)

    @property
    def properties(self) -> Mapping[str, str]:
        """Return OpenSlide-style string properties."""

        self._require_open()
        mpp_x, mpp_y = self._sdk_slide.mpp
        width, height = self.dimensions
        properties = {
            PROPERTY_NAME_VENDOR: "sqray",
            PROPERTY_NAME_COMMENT: "OpenSqray SDK-backed SDPC slide",
            PROPERTY_NAME_OBJECTIVE_POWER: _format_float(
                self._sdk_slide.magnification
            ),
            PROPERTY_NAME_MPP_X: _format_float(mpp_x),
            PROPERTY_NAME_MPP_Y: _format_float(mpp_y),
            PROPERTY_NAME_BOUNDS_X: "0",
            PROPERTY_NAME_BOUNDS_Y: "0",
            PROPERTY_NAME_BOUNDS_WIDTH: str(width),
            PROPERTY_NAME_BOUNDS_HEIGHT: str(height),
            "opensqray.backend": "sdk",
            "opensqray.format": "sdpc",
            "opensqray.schema_version": SDPC_METADATA_SCHEMA_VERSION,
            "opensqray.sdpc.version": self._info.version,
            "opensqray.sdpc.level_count": str(self.level_count),
            "opensqray.sdpc.tile_size": _format_size(self._sdk_slide.tile_size),
        }
        for level in range(self.level_count):
            properties[f"opensqray.sdk.level_downsample.{level}"] = _format_float(
                self._sdk_slide.level_downsample(level)
            )
        barcode = self._sdk_slide.barcode
        if barcode:
            properties["opensqray.sdpc.barcode"] = barcode
        for key in ("device_id", "acquired_at", "scanner_model", "objective"):
            value = self._info.metadata.get(key)
            if value is not None:
                properties[f"opensqray.sdpc.metadata.{key}"] = str(value)
        return MappingProxyType(properties)

    @property
    def associated_images(self) -> Mapping[str, object]:
        """Return decoded associated images keyed like OpenSlide."""

        self._require_open()
        if self._associated_images is None:
            images: dict[str, object] = {}
            for name in SDK_ASSOCIATED_IMAGE_TYPES:
                try:
                    _, data = self._sdk_slide.read_associated_jpeg_bytes(name)
                except SqraySDKError:
                    continue
                images[name] = decode_jpeg_bytes(data)
            self._associated_images = MappingProxyType(images)
        return self._associated_images

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> object:
        """Return a Pillow RGBA image for a slide region."""

        self._require_open()
        return image_from_bgra_bytes(
            self._sdk_slide.read_region_bgra_bytes(
                location=location,
                level=level,
                size=size,
            ),
            size,
        )

    def get_thumbnail(self, size: tuple[int, int]) -> object:
        """Return a thumbnail image constrained to ``size``."""

        self._require_open()
        if size[0] <= 0 or size[1] <= 0:
            raise ValueError("thumbnail size must be positive")

        associated = self.associated_images
        if "thumbnail" in associated:
            image = associated["thumbnail"].copy()
        elif "macro" in associated:
            image = associated["macro"].copy()
        else:
            level = self.get_best_level_for_downsample(
                max(
                    self.dimensions[0] / size[0],
                    self.dimensions[1] / size[1],
                )
            )
            image = self.read_region((0, 0), level, self.level_dimensions[level])
        image.thumbnail(size)
        image.load()
        return image

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Return the best OpenSlide-style pyramid level for ``downsample``."""

        self._require_open()
        if downsample <= 1:
            return 0
        downsamples = self.level_downsamples
        return min(
            range(len(downsamples)),
            key=lambda level: abs(downsamples[level] - downsample),
        )

    def read_tile_jpeg_bytes(self, *, level: int, tile_x: int, tile_y: int) -> bytes:
        """Return raw SDK tile JPEG bytes for applications that use tile reads."""

        self._require_open()
        return self._sdk_slide.read_tile_jpeg_bytes(
            level=level,
            tile_x=tile_x,
            tile_y=tile_y,
        )

    @property
    def info(self) -> SDPCInfo:
        """Return native OpenSqray SDPC metadata for diagnostics."""

        self._require_open()
        return self._info

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("OpenSqraySlide is closed")


def open_slide(path: str | Path, **kwargs: object) -> object:
    """Open SDPC with ``OpenSqraySlide`` and other formats with OpenSlide."""

    slide_path = Path(path)
    if is_sdpc(slide_path):
        return OpenSqraySlide(slide_path, **kwargs)

    try:
        import openslide
    except ImportError as exc:
        raise OpenSlideUnavailable(
            "OpenSlide support requires the openslide-python package and the "
            "native OpenSlide library for non-SDPC slides."
        ) from exc
    return openslide.OpenSlide(str(slide_path))


def is_sdpc(path: str | Path) -> bool:
    """Return true when the file has an SDPC signature."""

    with Path(path).open("rb") as handle:
        return handle.read(2) == b"SQ"


def _format_size(size: tuple[int, int]) -> str:
    return f"{size[0]}x{size[1]}"


def _format_float(value: float) -> str:
    return f"{value:g}"


def _level_downsamples(
    level_dimensions: tuple[tuple[int, int], ...],
) -> tuple[float, ...]:
    if not level_dimensions:
        return ()
    base_width, base_height = level_dimensions[0]
    downsamples: list[float] = []
    for width, height in level_dimensions:
        width_downsample = base_width / width if width else 1.0
        height_downsample = base_height / height if height else 1.0
        downsamples.append(max(width_downsample, height_downsample))
    return tuple(downsamples)
