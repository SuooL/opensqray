"""OpenSqray public APIs."""

from .batch import (
    RegionRequest,
    RegionResult,
    iter_regions,
    iter_patch_requests,
    read_regions,
    recommended_worker_count,
)
from .compat import (
    OpenSqraySlide,
    PROPERTY_NAME_BOUNDS_HEIGHT,
    PROPERTY_NAME_BOUNDS_WIDTH,
    PROPERTY_NAME_BOUNDS_X,
    PROPERTY_NAME_BOUNDS_Y,
    PROPERTY_NAME_COMMENT,
    PROPERTY_NAME_MPP_X,
    PROPERTY_NAME_MPP_Y,
    PROPERTY_NAME_OBJECTIVE_POWER,
    PROPERTY_NAME_VENDOR,
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
from .runtime_package import (
    RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION,
    check_runtime_package_layout,
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
from .sdk_validation import (
    OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
    summarize_sdk_validation,
    validate_sdk_runtime,
)
from .slide import SDPCSlide

__all__ = [
    "ImageDecodeUnavailable",
    "OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION",
    "OpenSqraySlide",
    "PROPERTY_NAME_BOUNDS_HEIGHT",
    "PROPERTY_NAME_BOUNDS_WIDTH",
    "PROPERTY_NAME_BOUNDS_X",
    "PROPERTY_NAME_BOUNDS_Y",
    "PROPERTY_NAME_COMMENT",
    "PROPERTY_NAME_MPP_X",
    "PROPERTY_NAME_MPP_Y",
    "PROPERTY_NAME_OBJECTIVE_POWER",
    "PROPERTY_NAME_VENDOR",
    "RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION",
    "SDPC_INDEX_RESEARCH_SCHEMA_VERSION",
    "SDPC_FIELD_CONFIDENCE",
    "SDPC_METADATA_SCHEMA_VERSION",
    "SDPCFormatError",
    "SDPCInfo",
    "SDPCSlide",
    "SqraySDKError",
    "SqraySDKSlide",
    "SqraySDKUnavailable",
    "RegionRequest",
    "RegionResult",
    "check_runtime_package_layout",
    "decode_jpeg_bytes",
    "image_from_bgra_bytes",
    "is_sdpc",
    "iter_regions",
    "iter_patch_requests",
    "extract_sdpc_associated_images",
    "open_slide",
    "read_sdpc",
    "read_sdpc_byte_range",
    "read_regions",
    "recommended_worker_count",
    "scan_sdpc_index_research",
    "summarize_sdk_validation",
    "validate_sdk_runtime",
]
