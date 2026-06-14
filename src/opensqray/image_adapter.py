"""Optional image decoding helpers."""

from __future__ import annotations

from io import BytesIO
import importlib


class ImageDecodeUnavailable(RuntimeError):
    """Raised when image decoding is requested but Pillow is unavailable."""


def decode_jpeg_bytes(data: bytes) -> object:
    """Decode JPEG bytes with Pillow and return a loaded image object.

    Pillow is imported lazily so core SDPC parsing and raw JPEG byte access keep
    working in minimal environments.
    """

    image_module = _load_pillow_image_module()
    image = image_module.open(BytesIO(data))
    image.load()
    return image


def _load_pillow_image_module() -> object:
    try:
        return importlib.import_module("PIL.Image")
    except ImportError as exc:
        raise ImageDecodeUnavailable(
            "Image decoding requires Pillow. Install the optional image "
            "dependency with `pip install -e \".[image]\"`, then retry."
        ) from exc
