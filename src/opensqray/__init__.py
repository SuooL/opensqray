"""OpenSqray public APIs."""

from .compat import (
    OpenSqraySlide,
    is_sdpc,
    open_slide,
)
from .image_adapter import (
    ImageDecodeUnavailable,
    decode_jpeg_bytes,
    image_from_bgra_bytes,
)
from .index_research import (
    SDPC_INDEX_RESEARCH_SCHEMA_VERSION,
    scan_sdpc_index_research,
)
from .sdpc import (
    SDPC_FIELD_CONFIDENCE,
    SDPC_METADATA_SCHEMA_VERSION,
    SDPCFormatError,
    SDPCInfo,
    extract_sdpc_associated_images,
    read_sdpc,
    read_sdpc_byte_range,
)
from .sdk_backend import SqraySDKError, SqraySDKSlide, SqraySDKUnavailable
from .slide import SDPCSlide

__all__ = [
    "ImageDecodeUnavailable",
    "OpenSqraySlide",
    "SDPC_INDEX_RESEARCH_SCHEMA_VERSION",
    "SDPC_FIELD_CONFIDENCE",
    "SDPC_METADATA_SCHEMA_VERSION",
    "SDPCFormatError",
    "SDPCInfo",
    "SDPCSlide",
    "SqraySDKError",
    "SqraySDKSlide",
    "SqraySDKUnavailable",
    "decode_jpeg_bytes",
    "image_from_bgra_bytes",
    "is_sdpc",
    "extract_sdpc_associated_images",
    "open_slide",
    "read_sdpc",
    "read_sdpc_byte_range",
    "scan_sdpc_index_research",
]
