"""Small DeepZoom adapter for OpenSqray/OpenSlide-like slide objects."""

from __future__ import annotations

from math import ceil, log2
from typing import Any


class OpenSqrayDeepZoomGenerator:
    """Generate DeepZoom-style tiles from a slide with ``read_region()``."""

    def __init__(
        self,
        slide: Any,
        *,
        tile_size: int = 254,
        overlap: int = 1,
        limit_bounds: bool = False,
    ) -> None:
        if tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if limit_bounds:
            raise NotImplementedError("limit_bounds is not implemented")

        self._slide = slide
        self._tile_size = tile_size
        self._overlap = overlap
        self._dimensions = tuple(int(value) for value in slide.dimensions)
        max_dimension = max(self._dimensions)
        self._level_count = int(ceil(log2(max_dimension))) + 1 if max_dimension else 1
        self._level_dimensions = tuple(
            self._deepzoom_level_dimensions(level)
            for level in range(self._level_count)
        )
        self._level_tiles = tuple(
            (
                int(ceil(width / tile_size)),
                int(ceil(height / tile_size)),
            )
            for width, height in self._level_dimensions
        )

    @property
    def level_count(self) -> int:
        return self._level_count

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return self._level_dimensions

    @property
    def level_tiles(self) -> tuple[tuple[int, int], ...]:
        return self._level_tiles

    @property
    def tile_count(self) -> int:
        return sum(columns * rows for columns, rows in self._level_tiles)

    def get_tile(
        self,
        level: int,
        address: tuple[int, int],
    ) -> object:
        """Return one DeepZoom tile image."""

        location, slide_level, size = self.get_tile_coordinates(level, address)
        tile = self._slide.read_region(location, slide_level, size)
        final_size = self.get_tile_dimensions(level, address)
        if getattr(tile, "size", None) != final_size:
            tile = tile.resize(final_size)
        return tile

    def get_tile_coordinates(
        self,
        level: int,
        address: tuple[int, int],
    ) -> tuple[tuple[int, int], int, tuple[int, int]]:
        """Return ``(location, slide_level, size)`` for a DeepZoom tile."""

        tile_bounds = self._tile_bounds(level, address)
        dz_downsample = self._deepzoom_downsample(level)
        location = (
            int(tile_bounds[0] * dz_downsample),
            int(tile_bounds[1] * dz_downsample),
        )
        slide_level = self._slide.get_best_level_for_downsample(dz_downsample)
        slide_downsample = self._slide.level_downsamples[slide_level]
        size = (
            int(ceil(tile_bounds[2] * dz_downsample / slide_downsample)),
            int(ceil(tile_bounds[3] * dz_downsample / slide_downsample)),
        )
        return location, slide_level, size

    def get_tile_dimensions(
        self,
        level: int,
        address: tuple[int, int],
    ) -> tuple[int, int]:
        """Return the DeepZoom pixel size for one tile."""

        tile_bounds = self._tile_bounds(level, address)
        return tile_bounds[2], tile_bounds[3]

    def get_dzi(self, format: str) -> str:
        """Return a minimal DZI XML descriptor."""

        width, height = self._dimensions
        return (
            f'<Image TileSize="{self._tile_size}" Overlap="{self._overlap}" '
            f'Format="{format}" '
            'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
            f'<Size Width="{width}" Height="{height}"/></Image>'
        )

    def _deepzoom_level_dimensions(self, level: int) -> tuple[int, int]:
        downsample = self._deepzoom_downsample(level)
        return (
            int(ceil(self._dimensions[0] / downsample)),
            int(ceil(self._dimensions[1] / downsample)),
        )

    def _deepzoom_downsample(self, level: int) -> int:
        self._validate_level(level)
        return 2 ** (self._level_count - level - 1)

    def _tile_bounds(
        self,
        level: int,
        address: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        self._validate_level(level)
        column, row = address
        columns, rows = self._level_tiles[level]
        if column < 0 or row < 0 or column >= columns or row >= rows:
            raise ValueError(f"tile address out of range: {address}")

        width, height = self._level_dimensions[level]
        left = self._overlap if column > 0 else 0
        top = self._overlap if row > 0 else 0
        right = self._overlap if column < columns - 1 else 0
        bottom = self._overlap if row < rows - 1 else 0
        x = column * self._tile_size - left
        y = row * self._tile_size - top
        tile_width = min(self._tile_size + left + right, width - x)
        tile_height = min(self._tile_size + top + bottom, height - y)
        return x, y, tile_width, tile_height

    def _validate_level(self, level: int) -> None:
        if level < 0 or level >= self._level_count:
            raise ValueError(f"level out of range: {level}")


DeepZoomGenerator = OpenSqrayDeepZoomGenerator
