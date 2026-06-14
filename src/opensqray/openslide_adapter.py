"""Optional OpenSlide integration."""

from __future__ import annotations

from pathlib import Path


class OpenSlideUnavailable(RuntimeError):
    """Raised when OpenSlide support is requested but unavailable."""


def inspect_with_openslide(path: str | Path) -> dict[str, object]:
    """Inspect a slide using OpenSlide.

    The import is intentionally local so SDPC metadata parsing has no OpenSlide
    dependency.
    """

    try:
        import openslide
    except ImportError as exc:
        raise OpenSlideUnavailable(
            "OpenSlide support requires the openslide-python package and the "
            "native OpenSlide library. Install the optional dependency and "
            "system library, then retry."
        ) from exc

    slide_path = Path(path)
    with openslide.OpenSlide(str(slide_path)) as slide:
        return {
            "format": "openslide",
            "path": str(slide_path),
            "dimensions": {
                "width": slide.dimensions[0],
                "height": slide.dimensions[1],
            },
            "level_count": slide.level_count,
            "level_dimensions": [
                {"width": width, "height": height}
                for width, height in slide.level_dimensions
            ],
            "level_downsamples": list(slide.level_downsamples),
            "properties": dict(slide.properties),
        }

