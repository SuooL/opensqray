"""SDPC metadata parsing.

The SDPC format is proprietary and currently only partially mapped. This module
parses fields that are stable across the inspected samples and labels less
certain values as experimental diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import BinaryIO


HEADER_READ_SIZE = 0x2000
METADATA_BLOCK_SIZE = 0x300
JPEG_MARKER = b"\xff\xd8\xff"
ACQUIRED_AT_PATTERN = re.compile(r"\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2}")
SDPC_METADATA_SCHEMA_VERSION = "opensqray.sdpc.metadata.v1"
SDPC_FIELD_CONFIDENCE = {
    "version": "high",
    "file_size": "high",
    "stored_file_size": "high",
    "file_size_matches_header": "high",
    "header_size": "high",
    "level_count": "high",
    "dimensions": "high",
    "tile_size": "high",
    "thumbnail_size": "high",
    "scan_magnification": "high",
    "metadata_offset": "high",
    "metadata.device_id": "medium",
    "metadata.acquired_at": "medium",
    "metadata.scanner_model": "medium",
    "metadata.objective": "medium",
    "metadata.embedded_strings": "diagnostic",
    "experimental.scale_hint_offset_0x48": "experimental",
    "experimental.pixel_size_hint_offset_0x4c": "experimental",
    "jpeg_streams.count": "diagnostic",
    "jpeg_streams.offsets_preview": "diagnostic",
}


class SDPCFormatError(ValueError):
    """Raised when a file cannot be interpreted as an SDPC file."""


@dataclass(frozen=True)
class SDPCInfo:
    """Parsed SDPC metadata."""

    path: str
    version: str
    file_size: int
    stored_file_size: int
    file_size_matches_header: bool
    header_size: int
    level_count: int
    dimensions: tuple[int, int]
    tile_size: tuple[int, int]
    thumbnail_size: tuple[int, int]
    scan_magnification: int | None
    metadata_offset: int
    metadata: dict[str, object]
    experimental: dict[str, object]
    jpeg_streams: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "format": "sdpc",
            "schema_version": SDPC_METADATA_SCHEMA_VERSION,
            "path": self.path,
            "version": self.version,
            "file_size": self.file_size,
            "stored_file_size": self.stored_file_size,
            "file_size_matches_header": self.file_size_matches_header,
            "header_size": self.header_size,
            "level_count": self.level_count,
            "dimensions": {
                "width": self.dimensions[0],
                "height": self.dimensions[1],
            },
            "tile_size": {
                "width": self.tile_size[0],
                "height": self.tile_size[1],
            },
            "thumbnail_size": {
                "width": self.thumbnail_size[0],
                "height": self.thumbnail_size[1],
            },
            "scan_magnification": self.scan_magnification,
            "metadata_offset": self.metadata_offset,
            "metadata": self.metadata,
            "experimental": self.experimental,
            "jpeg_streams": self.jpeg_streams,
            "field_confidence": dict(SDPC_FIELD_CONFIDENCE),
            "validation": self._validation_report(),
        }

    def _validation_report(self) -> dict[str, object]:
        warnings: list[dict[str, object]] = []
        if not self.file_size_matches_header:
            warnings.append(
                {
                    "code": "file_size_mismatch",
                    "message": (
                        "stored_file_size does not match the actual file size"
                    ),
                    "stored_file_size": self.stored_file_size,
                    "actual_file_size": self.file_size,
                }
            )

        return {"warnings": warnings}


def is_sdpc(path: str | Path) -> bool:
    """Return true when the file looks like an SDPC file."""

    path = Path(path)
    if path.suffix.lower() == ".sdpc":
        return True
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"SQ"
    except OSError:
        return False


def read_sdpc(
    path: str | Path,
    *,
    scan_jpegs: bool = False,
    jpeg_preview_limit: int = 20,
) -> SDPCInfo:
    """Read SDPC metadata from ``path``.

    ``scan_jpegs=False`` only returns a short preview of JPEG marker offsets.
    ``scan_jpegs=True`` scans the whole file and returns the marker count.
    """

    path = Path(path)
    file_size = path.stat().st_size

    with path.open("rb") as handle:
        header = handle.read(HEADER_READ_SIZE)
        if len(header) < 0x5C:
            raise SDPCFormatError("file is too small to contain an SDPC header")

        version = _read_version(header)
        header_size = _u32(header, 0x12)
        stored_file_size = _u32(header, 0x16)
        level_count = _u32(header, 0x26)
        width = _u32(header, 0x2A)
        height = _u32(header, 0x2E)
        tile_width = _u32(header, 0x32)
        tile_height = _u32(header, 0x36)
        thumbnail_width = _u32(header, 0x3A)
        thumbnail_height = _u32(header, 0x3E)
        scale_hint = _f32(header, 0x48)
        pixel_size_hint = _f64(header, 0x4C)
        scan_magnification = _optional_u32(header, 0x54)
        metadata_offset = _u32(header, 0x58)

        metadata_block = _read_metadata_block(handle, header, metadata_offset)

    metadata = _classify_metadata(_printable_strings(metadata_block))
    jpeg_streams = _scan_jpeg_markers(
        path,
        count_all=scan_jpegs,
        max_offsets=jpeg_preview_limit,
    )

    return SDPCInfo(
        path=str(path),
        version=version,
        file_size=file_size,
        stored_file_size=stored_file_size,
        file_size_matches_header=(stored_file_size == file_size),
        header_size=header_size,
        level_count=level_count,
        dimensions=(width, height),
        tile_size=(tile_width, tile_height),
        thumbnail_size=(thumbnail_width, thumbnail_height),
        scan_magnification=scan_magnification,
        metadata_offset=metadata_offset,
        metadata=metadata,
        experimental={
            "scale_hint_offset_0x48": scale_hint,
            "pixel_size_hint_offset_0x4c": pixel_size_hint,
        },
        jpeg_streams=jpeg_streams,
    )


def _read_version(header: bytes) -> str:
    version = header[:12].split(b"\0", 1)[0].decode("ascii", errors="replace")
    if not version.startswith("SQ"):
        raise SDPCFormatError("missing SDPC SQ signature")
    return version


def _u32(data: bytes, offset: int) -> int:
    _require_size(data, offset, 4)
    return struct.unpack_from("<I", data, offset)[0]


def _optional_u32(data: bytes, offset: int) -> int | None:
    value = _u32(data, offset)
    return value if value else None


def _f32(data: bytes, offset: int) -> float:
    _require_size(data, offset, 4)
    return struct.unpack_from("<f", data, offset)[0]


def _f64(data: bytes, offset: int) -> float:
    _require_size(data, offset, 8)
    return struct.unpack_from("<d", data, offset)[0]


def _require_size(data: bytes, offset: int, size: int) -> None:
    if len(data) < offset + size:
        raise SDPCFormatError(f"file ended before SDPC field at 0x{offset:x}")


def _read_metadata_block(
    handle: BinaryIO,
    header: bytes,
    metadata_offset: int,
) -> bytes:
    if metadata_offset <= 0:
        return b""
    end = metadata_offset + METADATA_BLOCK_SIZE
    if end <= len(header):
        return header[metadata_offset:end]

    handle.seek(metadata_offset)
    return handle.read(METADATA_BLOCK_SIZE)


def _printable_strings(data: bytes, *, min_length: int = 4) -> list[str]:
    strings: list[str] = []
    current = bytearray()

    for byte in data:
        if 32 <= byte <= 126:
            current.append(byte)
            continue
        if len(current) >= min_length:
            strings.append(current.decode("ascii", errors="replace"))
        current.clear()

    if len(current) >= min_length:
        strings.append(current.decode("ascii", errors="replace"))

    return strings


def _classify_metadata(strings: list[str]) -> dict[str, object]:
    acquired_at = _first_match_group(strings, ACQUIRED_AT_PATTERN)
    scanner_model = _first_matching(strings, re.compile(r"^SQ[A-Z0-9-]"))
    objective = _first_matching(strings, re.compile(r"(Plan|PLan|UPlan|UPLan|Apo).*\d+X$"))

    excluded = {value for value in (acquired_at, scanner_model, objective) if value}
    device_id = next((value for value in strings if value not in excluded), None)

    return {
        "device_id": device_id,
        "acquired_at": acquired_at,
        "scanner_model": scanner_model,
        "objective": objective,
        "embedded_strings": strings,
    }


def _first_matching(strings: list[str], pattern: re.Pattern[str]) -> str | None:
    return next((value for value in strings if pattern.search(value)), None)


def _first_match_group(strings: list[str], pattern: re.Pattern[str]) -> str | None:
    for value in strings:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return None


def _scan_jpeg_markers(
    path: Path,
    *,
    count_all: bool,
    max_offsets: int,
    chunk_size: int = 1024 * 1024,
) -> dict[str, object]:
    offsets: list[int] = []
    count = 0
    overlap = b""
    absolute = 0

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break

            data = overlap + chunk
            base = absolute - len(overlap)
            cursor = 0
            while True:
                marker_at = data.find(JPEG_MARKER, cursor)
                if marker_at < 0:
                    break

                offset = base + marker_at
                count += 1
                if len(offsets) < max_offsets:
                    offsets.append(offset)
                cursor = marker_at + 1

                if not count_all and len(offsets) >= max_offsets:
                    return {"count": None, "offsets_preview": offsets}

            absolute += len(chunk)
            overlap = data[-(len(JPEG_MARKER) - 1):]

    return {
        "count": count if count_all else None,
        "offsets_preview": offsets,
    }
