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
JPEG_EOI = b"\xff\xd9"
JPEG_HEADER_SCAN_SIZE = 64 * 1024
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}
JPEG_STANDALONE_MARKERS = {
    0x01,
    0xD0,
    0xD1,
    0xD2,
    0xD3,
    0xD4,
    0xD5,
    0xD6,
    0xD7,
}
ACQUIRED_AT_PATTERN = re.compile(
    r"\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2}"
)
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
    "jpeg_streams.records_preview": "diagnostic",
    "associated_images.count": "experimental",
    "associated_images.records": "experimental",
    "tile_index.status": "experimental",
    "tile_index.levels": "experimental",
    "tile_index.tiles_preview": "experimental",
    "tile_index.missing_tiles_preview": "experimental",
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
    associated_images: dict[str, object]
    tile_index: dict[str, object]

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
            "associated_images": self.associated_images,
            "tile_index": self.tile_index,
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


@dataclass(frozen=True)
class SDPCJPEGRecord:
    """A valid embedded JPEG stream discovered in an SDPC file."""

    index: int
    offset: int
    length: int
    dimensions: tuple[int, int]
    precision: int
    sof_marker: str

    @property
    def end_offset(self) -> int:
        """Return the first byte offset after this JPEG stream."""

        return self.offset + self.length

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "index": self.index,
            "offset": self.offset,
            "length": self.length,
            "end_offset": self.end_offset,
            "content_type": "image/jpeg",
            "dimensions": {
                "width": self.dimensions[0],
                "height": self.dimensions[1],
            },
            "precision": self.precision,
            "sof_marker": self.sof_marker,
        }


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

    ``scan_jpegs=False`` returns a preview of valid embedded JPEG records.
    ``scan_jpegs=True`` scans the whole file and returns the valid record count.
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
    jpeg_streams = _scan_jpeg_records(
        path,
        count_all=scan_jpegs,
        max_offsets=jpeg_preview_limit,
    )
    associated_images = _classify_associated_images(
        jpeg_streams["records_preview"],
        tile_size=(tile_width, tile_height),
        thumbnail_size=(thumbnail_width, thumbnail_height),
        preview_limited=bool(jpeg_streams["preview_limited"]),
    )
    tile_index = _build_tile_index(
        jpeg_streams["records_preview"],
        dimensions=(width, height),
        tile_size=(tile_width, tile_height),
        level_count=level_count,
        scan_complete=jpeg_streams["count"] is not None,
        preview_limited=bool(jpeg_streams["preview_limited"]),
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
        associated_images=associated_images,
        tile_index=tile_index,
    )


def extract_sdpc_associated_images(
    path: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    jpeg_preview_limit: int = 50,
) -> list[dict[str, object]]:
    """Extract associated-image JPEG candidates from ``path``.

    Extraction is conservative: only records classified under
    ``associated_images.records`` are written, existing files are preserved by
    default, and no image decoding dependency is required.
    """

    path = Path(path)
    output_dir = Path(output_dir)
    info = read_sdpc(path, jpeg_preview_limit=jpeg_preview_limit)
    records = {
        record["index"]: record
        for record in info.jpeg_streams["records_preview"]
        if isinstance(record.get("index"), int)
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[dict[str, object]] = []
    for candidate in info.associated_images["records"]:
        record_index = candidate["record_index"]
        record = records.get(record_index)
        if record is None:
            continue

        filename = _associated_image_filename(path, candidate)
        target = output_dir / filename
        if target.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing file: {target}")

        _copy_file_range(
            path,
            target,
            offset=int(record["offset"]),
            length=int(record["length"]),
        )
        extracted.append({**candidate, "output_path": str(target)})

    return extracted


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
    objective = _first_matching(
        strings,
        re.compile(r"(Plan|PLan|UPlan|UPLan|Apo).*\d+X$"),
    )

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


def _scan_jpeg_records(
    path: Path,
    *,
    count_all: bool,
    max_offsets: int,
    chunk_size: int = 1024 * 1024,
) -> dict[str, object]:
    records: list[SDPCJPEGRecord] = []
    count = 0
    overlap = b""
    absolute = 0
    preview_limited = False

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
                record = _read_jpeg_record(path, offset, count)
                if record is not None:
                    count += 1
                    if len(records) < max_offsets:
                        records.append(record)
                    else:
                        preview_limited = True
                    if preview_limited and not count_all:
                        return _jpeg_stream_summary(records, None, preview_limited)
                cursor = marker_at + 1

            absolute += len(chunk)
            overlap = data[-(len(JPEG_MARKER) - 1):]

    return _jpeg_stream_summary(records, count, preview_limited)


def _jpeg_stream_summary(
    records: list[SDPCJPEGRecord],
    count: int | None,
    preview_limited: bool,
) -> dict[str, object]:
    return {
        "count": count,
        "offsets_preview": [record.offset for record in records],
        "records_preview": [record.to_dict() for record in records],
        "preview_limited": preview_limited,
    }


def _read_jpeg_record(
    path: Path,
    offset: int,
    index: int,
) -> SDPCJPEGRecord | None:
    dimensions = _read_jpeg_dimensions(path, offset)
    if dimensions is None:
        return None

    length = _find_jpeg_length(path, offset)
    if length is None:
        return None

    width, height, precision, sof_marker = dimensions
    return SDPCJPEGRecord(
        index=index,
        offset=offset,
        length=length,
        dimensions=(width, height),
        precision=precision,
        sof_marker=sof_marker,
    )


def _read_jpeg_dimensions(
    path: Path,
    offset: int,
    max_scan: int = JPEG_HEADER_SCAN_SIZE,
) -> tuple[int, int, int, str] | None:
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(max_scan)

    if not data.startswith(b"\xff\xd8"):
        return None

    cursor = 2
    while cursor + 4 <= len(data):
        if data[cursor] != 0xFF:
            return None

        while cursor < len(data) and data[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(data):
            return None

        marker = data[cursor]
        cursor += 1
        if marker == 0x00:
            return None
        if marker in JPEG_STANDALONE_MARKERS:
            continue
        if marker == 0xDA:
            return None
        if marker in (0xD8, 0xD9):
            return None
        if cursor + 2 > len(data):
            return None

        segment_length = int.from_bytes(data[cursor:cursor + 2], "big")
        if segment_length < 2:
            return None
        segment_end = cursor + segment_length
        if segment_end > len(data):
            return None

        if marker in JPEG_SOF_MARKERS and segment_length >= 7:
            precision = data[cursor + 2]
            height = int.from_bytes(data[cursor + 3:cursor + 5], "big")
            width = int.from_bytes(data[cursor + 5:cursor + 7], "big")
            if width <= 0 or height <= 0:
                return None
            return width, height, precision, f"0x{marker:02x}"

        cursor = segment_end

    return None


def _find_jpeg_length(
    path: Path,
    offset: int,
    chunk_size: int = 1024 * 1024,
) -> int | None:
    overlap = b""
    consumed = 0
    with path.open("rb") as handle:
        handle.seek(offset)
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                return None

            data = overlap + chunk
            marker_at = data.find(JPEG_EOI)
            if marker_at >= 0:
                return consumed - len(overlap) + marker_at + len(JPEG_EOI)

            consumed += len(chunk)
            overlap = data[-(len(JPEG_EOI) - 1):]


def _classify_associated_images(
    records: list[dict[str, object]],
    *,
    tile_size: tuple[int, int],
    thumbnail_size: tuple[int, int],
    preview_limited: bool,
) -> dict[str, object]:
    candidates, tile_found = _leading_non_tile_records(records, tile_size)
    named = _name_associated_candidates(candidates, thumbnail_size)
    limitations = [
        "Candidate role names are not formal SDPC directory entries yet.",
        "Only embedded JPEG streams with parseable dimensions are considered.",
    ]
    if preview_limited and not tile_found:
        limitations.append(
            "JPEG preview ended before a tile-sized record was observed; "
            "candidate classification may be incomplete."
        )

    return {
        "count": len(named),
        "records": named,
        "strategy": "leading_non_tile_jpegs_before_first_tile_sized_record",
        "confidence": "heuristic",
        "limitations": limitations,
    }


def _leading_non_tile_records(
    records: list[dict[str, object]],
    tile_size: tuple[int, int],
) -> tuple[list[dict[str, object]], bool]:
    candidates: list[dict[str, object]] = []
    for record in records:
        dimensions = _record_dimensions(record)
        if dimensions == tile_size:
            return candidates, True
        candidates.append(record)
    return candidates, False


def _name_associated_candidates(
    candidates: list[dict[str, object]],
    thumbnail_size: tuple[int, int],
) -> list[dict[str, object]]:
    if not candidates:
        return []

    names: dict[int, str] = {}
    for position, record in enumerate(candidates):
        if _record_dimensions(record) == thumbnail_size:
            names[position] = "thumbnail"

    unnamed = [i for i in range(len(candidates)) if i not in names]
    if len(unnamed) >= 2:
        largest = max(unnamed, key=lambda i: _record_area(candidates[i]))
        names[largest] = "macro_candidate"
        for i in unnamed:
            if i not in names:
                names[i] = (
                    "label_candidate"
                    if len(unnamed) == 2
                    else f"associated_candidate_{i}"
                )
    elif len(unnamed) == 1:
        names[unnamed[0]] = "associated_candidate"

    output: list[dict[str, object]] = []
    for position, record in enumerate(candidates):
        dimensions = record["dimensions"]
        output.append(
            {
                "name": names[position],
                "record_index": record["index"],
                "offset": record["offset"],
                "length": record["length"],
                "content_type": "image/jpeg",
                "dimensions": dimensions,
                "confidence": "heuristic",
                "reason": (
                    "leading non-tile JPEG stream before the first "
                    "tile-sized JPEG record"
                ),
            }
        )

    return output


def _build_tile_index(
    records: list[dict[str, object]],
    *,
    dimensions: tuple[int, int],
    tile_size: tuple[int, int],
    level_count: int,
    scan_complete: bool,
    preview_limited: bool,
) -> dict[str, object]:
    levels = _expected_tile_levels(dimensions, tile_size, level_count)
    tile_records, non_tile_after_start = _tile_sized_records(records, tile_size)
    total_expected_tiles = sum(int(level["expected_tiles"]) for level in levels)

    if not tile_records:
        return {
            "status": "unavailable",
            "strategy": "sequential_tile_sized_jpeg_records_after_associated_candidates",
            "confidence": "unavailable",
            "levels": levels,
            "tiles_preview": [],
            "observed_tile_count": 0 if scan_complete and not preview_limited else None,
            "expected_tile_count": total_expected_tiles,
            "missing_tile_count": None,
            "missing_tiles_preview": [],
            "preview_limited": preview_limited,
            "limitations": [
                "No tile-sized JPEG record was found in the available preview.",
                "The formal SDPC tile index table has not been mapped yet.",
            ],
        }

    tiles_preview = [
        _tile_preview_record(record, sequence_index, levels, tile_size)
        for sequence_index, record in enumerate(tile_records)
    ]
    level_summaries = _summarize_tile_levels(levels, tiles_preview)
    complete_preview = scan_complete and not preview_limited
    missing_tile_count = None
    missing_tiles_preview: list[dict[str, object]] = []
    if complete_preview:
        missing_tile_count = max(total_expected_tiles - len(tile_records), 0)
        missing_tiles_preview = _missing_tile_preview(
            start_sequence_index=len(tile_records),
            levels=levels,
            tile_size=tile_size,
            max_items=20,
        )

    limitations = [
        "Tile coordinates are row-major candidates inferred from sequential "
        "tile-sized JPEG records.",
        "The formal SDPC tile index table has not been mapped yet.",
        "Sparse scans and non-standard ordering remain experimental.",
    ]
    if preview_limited:
        limitations.append(
            "JPEG record preview is limited; later tile records may not be shown."
        )
    if non_tile_after_start:
        limitations.append(
            "Non-tile-sized JPEG records were observed after the first tile-sized "
            "record and were not mapped as tiles."
        )

    return {
        "status": "candidate",
        "strategy": "sequential_tile_sized_jpeg_records_after_associated_candidates",
        "confidence": "heuristic",
        "levels": level_summaries,
        "tiles_preview": tiles_preview,
        "observed_tile_count": len(tile_records) if complete_preview else None,
        "expected_tile_count": total_expected_tiles,
        "missing_tile_count": missing_tile_count,
        "missing_tiles_preview": missing_tiles_preview,
        "preview_limited": preview_limited,
        "limitations": limitations,
    }


def _expected_tile_levels(
    dimensions: tuple[int, int],
    tile_size: tuple[int, int],
    level_count: int,
) -> list[dict[str, object]]:
    levels: list[dict[str, object]] = []
    for level in range(level_count):
        scale = 2 ** level
        width = _ceil_div(dimensions[0], scale)
        height = _ceil_div(dimensions[1], scale)
        columns = _ceil_div(width, tile_size[0])
        rows = _ceil_div(height, tile_size[1])
        expected_tiles = columns * rows
        first_sequence_index = sum(
            int(previous["expected_tiles"]) for previous in levels
        )
        levels.append(
            {
                "level": level,
                "dimensions": {"width": width, "height": height},
                "grid": {"columns": columns, "rows": rows},
                "expected_tiles": expected_tiles,
                "first_sequence_index": first_sequence_index,
                "last_sequence_index": first_sequence_index + expected_tiles - 1,
            }
        )
    return levels


def _tile_sized_records(
    records: list[dict[str, object]],
    tile_size: tuple[int, int],
) -> tuple[list[dict[str, object]], bool]:
    tile_records: list[dict[str, object]] = []
    found_first_tile = False
    non_tile_after_start = False
    for record in records:
        dimensions = _record_dimensions(record)
        if dimensions == tile_size:
            found_first_tile = True
            tile_records.append(record)
            continue
        if found_first_tile:
            non_tile_after_start = True

    return tile_records, non_tile_after_start


def _tile_preview_record(
    record: dict[str, object],
    sequence_index: int,
    levels: list[dict[str, object]],
    tile_size: tuple[int, int],
) -> dict[str, object]:
    level, local_index = _locate_tile_sequence(sequence_index, levels)
    grid = level["grid"]
    columns = int(grid["columns"])
    tile_x = local_index % columns
    tile_y = local_index // columns
    valid_size = _tile_valid_size(level, tile_x, tile_y, tile_size)
    dimensions = record["dimensions"]
    return {
        "record_index": record["index"],
        "sequence_index": sequence_index,
        "level": level["level"],
        "tile_x": tile_x,
        "tile_y": tile_y,
        "offset": record["offset"],
        "length": record["length"],
        "content_type": "image/jpeg",
        "dimensions": dimensions,
        "valid_size": valid_size,
        "padded": valid_size != dimensions,
        "confidence": "heuristic",
    }


def _locate_tile_sequence(
    sequence_index: int,
    levels: list[dict[str, object]],
) -> tuple[dict[str, object], int]:
    for level in levels:
        first = int(level["first_sequence_index"])
        last = int(level["last_sequence_index"])
        if first <= sequence_index <= last:
            return level, sequence_index - first
    return levels[-1], sequence_index - int(levels[-1]["first_sequence_index"])


def _tile_valid_size(
    level: dict[str, object],
    tile_x: int,
    tile_y: int,
    tile_size: tuple[int, int],
) -> dict[str, int]:
    dimensions = level["dimensions"]
    width = int(dimensions["width"])
    height = int(dimensions["height"])
    valid_width = min(tile_size[0], max(width - tile_x * tile_size[0], 0))
    valid_height = min(tile_size[1], max(height - tile_y * tile_size[1], 0))
    return {"width": valid_width, "height": valid_height}


def _summarize_tile_levels(
    levels: list[dict[str, object]],
    tiles_preview: list[dict[str, object]],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for level in levels:
        preview_tiles = [
            tile for tile in tiles_preview if tile["level"] == level["level"]
        ]
        item = dict(level)
        item["preview_tile_count"] = len(preview_tiles)
        item["preview_complete"] = len(preview_tiles) == level["expected_tiles"]
        output.append(item)
    return output


def _missing_tile_preview(
    *,
    start_sequence_index: int,
    levels: list[dict[str, object]],
    tile_size: tuple[int, int],
    max_items: int,
) -> list[dict[str, object]]:
    missing: list[dict[str, object]] = []
    total_expected = sum(int(level["expected_tiles"]) for level in levels)
    for sequence_index in range(start_sequence_index, total_expected):
        level, local_index = _locate_tile_sequence(sequence_index, levels)
        columns = int(level["grid"]["columns"])
        tile_x = local_index % columns
        tile_y = local_index // columns
        missing.append(
            {
                "sequence_index": sequence_index,
                "level": level["level"],
                "tile_x": tile_x,
                "tile_y": tile_y,
                "valid_size": _tile_valid_size(
                    level,
                    tile_x,
                    tile_y,
                    tile_size,
                ),
            }
        )
        if len(missing) >= max_items:
            break
    return missing


def _record_dimensions(record: dict[str, object]) -> tuple[int, int] | None:
    dimensions = record.get("dimensions")
    if not isinstance(dimensions, dict):
        return None
    width = dimensions.get("width")
    height = dimensions.get("height")
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    return width, height


def _record_area(record: dict[str, object]) -> int:
    dimensions = _record_dimensions(record)
    if dimensions is None:
        return 0
    return dimensions[0] * dimensions[1]


def _ceil_div(value: int, divisor: int) -> int:
    if divisor <= 0:
        raise SDPCFormatError("SDPC tile dimensions must be positive")
    return (value + divisor - 1) // divisor


def _associated_image_filename(
    path: Path,
    candidate: dict[str, object],
) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(candidate["name"])).strip("-")
    return f"{path.stem}-{int(candidate['record_index']):04d}-{name}.jpg"


def _copy_file_range(
    source: Path,
    target: Path,
    *,
    offset: int,
    length: int,
    chunk_size: int = 1024 * 1024,
) -> None:
    remaining = length
    with source.open("rb") as source_handle, target.open("wb") as target_handle:
        source_handle.seek(offset)
        while remaining > 0:
            chunk = source_handle.read(min(chunk_size, remaining))
            if not chunk:
                raise SDPCFormatError("file ended while extracting JPEG stream")
            target_handle.write(chunk)
            remaining -= len(chunk)
