"""Research diagnostics for locating SDPC index-like structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from .sdpc import read_sdpc, read_sdpc_byte_range


SDPC_INDEX_RESEARCH_SCHEMA_VERSION = "opensqray.sdpc.index_research.v4"
INDEX_RESEARCH_ENCODINGS = {
    "uint32le": ("<I", 4),
    "uint64le": ("<Q", 8),
}


@dataclass(frozen=True)
class SearchWindow:
    """A non-JPEG byte window searched for index-like packed values."""

    name: str
    offset: int
    length: int

    @property
    def end_offset(self) -> int:
        return self.offset + self.length

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "offset": self.offset,
            "length": self.length,
            "end_offset": self.end_offset,
        }


def scan_sdpc_index_research(
    path: str | Path,
    *,
    scan_jpegs: bool = False,
    jpeg_preview_limit: int = 50,
    max_window_bytes: int = 2 * 1024 * 1024,
    min_table_matches: int = 2,
    candidate_limit: int = 50,
    context_bytes: int = 16,
) -> dict[str, object]:
    """Search for diagnostic index-table candidates in an SDPC file.

    The scanner looks only in non-JPEG windows before or between valid JPEG
    records from the current preview. It reports packed integer runs that match
    known JPEG record offsets, end offsets, or lengths.
    """

    if jpeg_preview_limit <= 0:
        raise ValueError("jpeg_preview_limit must be positive")
    if max_window_bytes <= 0:
        raise ValueError("max_window_bytes must be positive")
    if min_table_matches <= 0:
        raise ValueError("min_table_matches must be positive")
    if candidate_limit <= 0:
        raise ValueError("candidate_limit must be positive")
    if context_bytes < 0:
        raise ValueError("context_bytes must be non-negative")

    path = Path(path)
    info = read_sdpc(
        path,
        scan_jpegs=scan_jpegs,
        jpeg_preview_limit=jpeg_preview_limit,
    )
    records = _jpeg_records(info.jpeg_streams.get("records_preview", []))
    windows = _search_windows(
        records,
        first_jpeg_offset=records[0]["offset"] if records else None,
        max_window_bytes=max_window_bytes,
    )
    candidate_tables: list[dict[str, object]] = []
    for window in windows:
        data = read_sdpc_byte_range(path, offset=window.offset, length=window.length)
        candidate_tables.extend(
            _window_candidates(
                data,
                window,
                records,
                min_table_matches=min_table_matches,
                context_bytes=context_bytes,
            )
        )
    _attach_length_reconstructions(
        candidate_tables,
        records,
        tile_record_indexes=_tile_candidate_record_indexes(info.tile_index),
        expected_tile_levels=_expected_tile_levels(info.tile_index),
    )

    candidate_tables.sort(
        key=lambda item: (
            -int(item["match_count"]),
            int(item["offset"]),
            str(item["target"]),
            str(item["encoding"]),
        )
    )
    limited = len(candidate_tables) > candidate_limit

    return {
        "format": "sdpc",
        "schema_version": SDPC_INDEX_RESEARCH_SCHEMA_VERSION,
        "path": str(path),
        "strategy": "packed_known_jpeg_record_fields_in_non_jpeg_windows",
        "jpeg_record_count": info.jpeg_streams.get("count"),
        "jpeg_record_preview_count": len(records),
        "preview_limited": bool(info.jpeg_streams.get("preview_limited")),
        "context_bytes": context_bytes,
        "search_windows": [window.to_dict() for window in windows],
        "candidate_table_count": len(candidate_tables),
        "candidate_limited": limited,
        "candidate_tables": candidate_tables[:candidate_limit],
        "limitations": [
            "This is a research diagnostic, not a parsed SDPC tile directory.",
            "Only non-JPEG windows before or between previewed JPEG records are searched.",
            "Packed value matches can be coincidental and require manual validation.",
            "Absence of candidates does not prove that no SDPC index table exists.",
        ],
    }


def _jpeg_records(records: object) -> list[dict[str, int]]:
    output: list[dict[str, int]] = []
    if not isinstance(records, list):
        return output

    for record in records:
        if not isinstance(record, dict):
            continue
        index = record.get("index")
        offset = record.get("offset")
        end_offset = record.get("end_offset")
        length = record.get("length")
        if (
            type(index) is int
            and type(offset) is int
            and type(end_offset) is int
            and type(length) is int
            and offset >= 0
            and end_offset >= offset
            and length >= 0
        ):
            output.append(
                {
                    "index": index,
                    "offset": offset,
                    "end_offset": end_offset,
                    "length": length,
                }
            )

    return output


def _search_windows(
    records: list[dict[str, int]],
    *,
    first_jpeg_offset: int | None,
    max_window_bytes: int,
) -> list[SearchWindow]:
    windows: list[SearchWindow] = []
    if first_jpeg_offset is not None and first_jpeg_offset > 0:
        windows.append(
            _bounded_window(
                "before_first_jpeg",
                offset=0,
                length=first_jpeg_offset,
                max_window_bytes=max_window_bytes,
            )
        )

    previous = None
    for record in records:
        if previous is None:
            previous = record
            continue

        gap_offset = previous["end_offset"]
        gap_length = record["offset"] - gap_offset
        if gap_length > 0:
            windows.append(
                _bounded_window(
                    f"gap_after_record_{previous['index']}",
                    offset=gap_offset,
                    length=gap_length,
                    max_window_bytes=max_window_bytes,
                )
            )
        previous = record

    return [window for window in windows if window.length > 0]


def _bounded_window(
    name: str,
    *,
    offset: int,
    length: int,
    max_window_bytes: int,
) -> SearchWindow:
    return SearchWindow(name=name, offset=offset, length=min(length, max_window_bytes))


def _window_candidates(
    data: bytes,
    window: SearchWindow,
    records: list[dict[str, int]],
    *,
    min_table_matches: int,
    context_bytes: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for target, values in _target_series(records).items():
        for encoding, (fmt, width) in INDEX_RESEARCH_ENCODINGS.items():
            candidates.extend(
                _packed_run_candidates(
                    data,
                    values,
                    window=window,
                    target=target,
                    encoding=encoding,
                    fmt=fmt,
                    width=width,
                    min_table_matches=min_table_matches,
                    context_bytes=context_bytes,
                )
            )
    return _deduplicate_candidates(candidates)


def _target_series(records: list[dict[str, int]]) -> dict[str, list[int]]:
    return {
        "offset": [record["offset"] for record in records],
        "end_offset": [record["end_offset"] for record in records],
        "length": [record["length"] for record in records],
    }


def _packed_run_candidates(
    data: bytes,
    values: list[int],
    *,
    window: SearchWindow,
    target: str,
    encoding: str,
    fmt: str,
    width: int,
    min_table_matches: int,
    context_bytes: int,
) -> list[dict[str, object]]:
    if len(values) < min_table_matches:
        return []

    candidates: list[dict[str, object]] = []
    for value_index, value in enumerate(values):
        if value < 0:
            continue
        encoded = _pack_value(value, fmt)
        if encoded is None:
            continue

        cursor = 0
        while True:
            relative_offset = data.find(encoded, cursor)
            if relative_offset < 0:
                break

            match_count = _count_packed_run(
                data,
                values[value_index:],
                relative_offset=relative_offset,
                fmt=fmt,
                width=width,
            )
            if match_count >= min_table_matches:
                byte_length = match_count * width
                table_end = window.offset + relative_offset + byte_length
                candidates.append(
                    {
                        "target": target,
                        "encoding": encoding,
                        "window": window.name,
                        "window_relative_offset": relative_offset,
                        "offset": window.offset + relative_offset,
                        "end_offset": table_end,
                        "byte_length": byte_length,
                        "match_count": match_count,
                        "start_record_index": value_index,
                        "end_record_index": value_index + match_count - 1,
                        "distance_to_window_end": (
                            window.end_offset - table_end
                        ),
                        "context": _candidate_context(
                            data,
                            relative_offset=relative_offset,
                            byte_length=byte_length,
                            context_bytes=context_bytes,
                        ),
                        "values_preview": values[
                            value_index:value_index + min(match_count, 8)
                        ],
                        "confidence": "diagnostic",
                    }
                )
            cursor = relative_offset + 1

    return candidates


def _candidate_context(
    data: bytes,
    *,
    relative_offset: int,
    byte_length: int,
    context_bytes: int,
) -> dict[str, object]:
    before_start = max(0, relative_offset - context_bytes)
    before = data[before_start:relative_offset]
    after_start = relative_offset + byte_length
    after = data[after_start:after_start + context_bytes]
    return {
        "bytes_before": len(before),
        "before_hex": before.hex(),
        "bytes_after": len(after),
        "after_hex": after.hex(),
    }


def _count_packed_run(
    data: bytes,
    values: list[int],
    *,
    relative_offset: int,
    fmt: str,
    width: int,
) -> int:
    count = 0
    for value in values:
        encoded = _pack_value(value, fmt)
        if encoded is None:
            break
        start = relative_offset + count * width
        end = start + width
        if data[start:end] != encoded:
            break
        count += 1
    return count


def _pack_value(value: int, fmt: str) -> bytes | None:
    try:
        return struct.pack(fmt, value)
    except struct.error:
        return None


def _deduplicate_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    unique: list[dict[str, object]] = []
    for candidate in candidates:
        key = (
            candidate["target"],
            candidate["encoding"],
            candidate["window"],
            candidate["offset"],
            candidate["start_record_index"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    unique.sort(
        key=lambda item: (
            str(item["target"]),
            str(item["encoding"]),
            str(item["window"]),
            int(item["offset"]),
            -int(item["match_count"]),
        )
    )
    output: list[dict[str, object]] = []
    for candidate in unique:
        if _is_contained_in_existing_candidate(candidate, output):
            continue
        output.append(candidate)

    return output


def _is_contained_in_existing_candidate(
    candidate: dict[str, object],
    existing: list[dict[str, object]],
) -> bool:
    candidate_offset = int(candidate["offset"])
    candidate_end = candidate_offset + int(candidate["byte_length"])
    for other in existing:
        if (
            other["target"] != candidate["target"]
            or other["encoding"] != candidate["encoding"]
            or other["window"] != candidate["window"]
        ):
            continue

        other_offset = int(other["offset"])
        other_end = other_offset + int(other["byte_length"])
        if other_offset <= candidate_offset and candidate_end <= other_end:
            return True

    return False


def _attach_length_reconstructions(
    candidates: list[dict[str, object]],
    records: list[dict[str, int]],
    *,
    tile_record_indexes: set[int],
    expected_tile_levels: list[dict[str, object]],
) -> None:
    for candidate in candidates:
        if candidate.get("target") != "length":
            continue
        candidate["length_reconstruction"] = _length_reconstruction(
            candidate,
            records,
            tile_record_indexes=tile_record_indexes,
        )
        candidate["length_table_extent"] = _length_table_extent(
            candidate,
            expected_tile_levels=expected_tile_levels,
        )


def _length_reconstruction(
    candidate: dict[str, object],
    records: list[dict[str, int]],
    *,
    tile_record_indexes: set[int],
) -> dict[str, object]:
    start = int(candidate["start_record_index"])
    match_count = int(candidate["match_count"])
    matched_records = records[start:start + match_count]
    if not matched_records:
        return {
            "status": "unavailable",
            "reason": "candidate record range is outside the current preview",
            "confidence": "diagnostic",
        }

    first_record = matched_records[0]
    first_record_offset = first_record["offset"]
    derived_offsets: list[int] = []
    derived_end_offsets: list[int] = []
    derived_records: list[dict[str, object]] = []
    cursor = first_record_offset
    previous_observed_end: int | None = None
    adjacent_pair_count = 0

    for preview_position, record in enumerate(matched_records, start=start):
        derived_offset = cursor
        derived_end_offset = derived_offset + record["length"]
        offset_matches = derived_offset == record["offset"]
        end_offset_matches = derived_end_offset == record["end_offset"]
        if (
            previous_observed_end is not None
            and record["offset"] == previous_observed_end
        ):
            adjacent_pair_count += 1

        derived_offsets.append(derived_offset)
        derived_end_offsets.append(derived_end_offset)
        derived_records.append(
            {
                "preview_position": preview_position,
                "record_index": record["index"],
                "table_length": record["length"],
                "derived_offset": derived_offset,
                "derived_end_offset": derived_end_offset,
                "observed_offset": record["offset"],
                "observed_end_offset": record["end_offset"],
                "offset_matches": offset_matches,
                "end_offset_matches": end_offset_matches,
            }
        )
        cursor = derived_end_offset
        previous_observed_end = record["end_offset"]

    matched_offset_count = sum(
        1 for item in derived_records if item["offset_matches"]
    )
    matched_end_offset_count = sum(
        1 for item in derived_records if item["end_offset_matches"]
    )
    first_tile_offset = (
        first_record_offset
        if first_record["index"] in tile_record_indexes
        else None
    )

    return {
        "status": "candidate",
        "strategy": "cumulative_lengths_from_first_preview_record_offset",
        "length_table_record_range": {
            "start_preview_position": start,
            "end_preview_position": start + len(matched_records) - 1,
            "start_record_index": first_record["index"],
            "end_record_index": matched_records[-1]["index"],
        },
        "first_record_offset": first_record_offset,
        "first_tile_offset": first_tile_offset,
        "derived_offsets": derived_offsets,
        "derived_end_offsets": derived_end_offsets,
        "matched_offset_count": matched_offset_count,
        "matched_end_offset_count": matched_end_offset_count,
        "matches_preview_offsets": matched_offset_count == len(matched_records),
        "matches_preview_end_offsets": (
            matched_end_offset_count == len(matched_records)
        ),
        "observed_adjacent_pair_count": adjacent_pair_count,
        "all_preview_records_adjacent": adjacent_pair_count == max(
            len(matched_records) - 1,
            0,
        ),
        "derived_records_preview": derived_records[:8],
        "confidence": "diagnostic",
        "limitations": [
            "Reconstruction is anchored to the first matched preview record offset.",
            "It validates whether matched byte lengths reproduce preview offsets; "
            "it does not identify tile coordinates or a complete SDPC directory.",
        ],
    }


def _tile_candidate_record_indexes(tile_index: object) -> set[int]:
    if not isinstance(tile_index, dict):
        return set()
    tiles_preview = tile_index.get("tiles_preview")
    if not isinstance(tiles_preview, list):
        return set()

    output: set[int] = set()
    for tile in tiles_preview:
        if not isinstance(tile, dict):
            continue
        record_index = tile.get("record_index")
        if type(record_index) is int:
            output.add(record_index)
    return output


def _expected_tile_levels(tile_index: object) -> list[dict[str, object]]:
    if not isinstance(tile_index, dict):
        return []
    levels = tile_index.get("levels")
    if not isinstance(levels, list):
        return []

    output: list[dict[str, object]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        level_index = level.get("level")
        expected_tiles = level.get("expected_tiles")
        if type(level_index) is not int or type(expected_tiles) is not int:
            continue
        output.append(
            {
                "level": level_index,
                "expected_tiles": expected_tiles,
                "grid": level.get("grid"),
                "dimensions": level.get("dimensions"),
                "first_sequence_index": level.get("first_sequence_index"),
                "last_sequence_index": level.get("last_sequence_index"),
            }
        )
    return output


def _length_table_extent(
    candidate: dict[str, object],
    *,
    expected_tile_levels: list[dict[str, object]],
) -> dict[str, object]:
    encoding = str(candidate["encoding"])
    width = INDEX_RESEARCH_ENCODINGS.get(encoding, ("", 0))[1]
    if width <= 0:
        return {
            "status": "unavailable",
            "reason": f"unsupported candidate encoding: {encoding}",
            "confidence": "diagnostic",
        }

    bytes_to_window_end = int(candidate["byte_length"]) + int(
        candidate["distance_to_window_end"]
    )
    value_slots_to_window_end = bytes_to_window_end // width
    trailing_bytes_to_window_end = bytes_to_window_end % width
    matching_levels = [
        level
        for level in expected_tile_levels
        if level["expected_tiles"] == value_slots_to_window_end
    ]

    return {
        "status": "candidate",
        "strategy": "candidate_offset_to_search_window_end_value_slots",
        "value_width": width,
        "byte_length_to_window_end": bytes_to_window_end,
        "value_slots_to_window_end": value_slots_to_window_end,
        "trailing_bytes_to_window_end": trailing_bytes_to_window_end,
        "candidate_match_count": int(candidate["match_count"]),
        "unpreviewed_value_slots": max(
            value_slots_to_window_end - int(candidate["match_count"]),
            0,
        ),
        "expected_tile_level_matches": matching_levels,
        "matches_any_expected_level_tile_count": bool(matching_levels),
        "confidence": "diagnostic",
        "limitations": [
            "The extent assumes the current non-JPEG search window ends at the "
            "table boundary.",
            "A value-slot count matching an expected level tile count is "
            "structural evidence only, not a parsed SDPC directory.",
        ],
    }
