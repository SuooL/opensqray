from __future__ import annotations

from pathlib import Path
import struct


def make_jpeg_fixture(width: int, height: int, payload: bytes) -> bytes:
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )
    sos = b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    return b"\xff\xd8" + sof0 + sos + payload + b"\xff\xd9"


def make_sdpc_fixture(path: Path, *, stored_file_size: int | None = None) -> None:
    data = bytearray(12000)
    data[:12] = b"SQ1.1.9.0430"
    struct.pack_into("<I", data, 0x12, 156)
    struct.pack_into("<I", data, 0x16, stored_file_size or len(data))
    struct.pack_into("<I", data, 0x26, 4)
    struct.pack_into("<I", data, 0x2A, 26880)
    struct.pack_into("<I", data, 0x2E, 21504)
    struct.pack_into("<I", data, 0x32, 672)
    struct.pack_into("<I", data, 0x36, 672)
    struct.pack_into("<I", data, 0x3A, 302)
    struct.pack_into("<I", data, 0x3E, 241)
    struct.pack_into("<f", data, 0x48, 0.25)
    struct.pack_into("<d", data, 0x4C, 0.104538690)
    struct.pack_into("<I", data, 0x54, 40)
    struct.pack_into("<I", data, 0x58, 0x1B34)

    metadata = (
        b"EI\x00\x03\x00\x00\x00\x00"
        b"FV-025GN-X1C\x00"
        b"2022/5/14 14:58:34\x00"
        b"SQS120P-20220006\x00"
        b"UPlanApo40X\x00"
    )
    data[0x1B34:0x1B34 + len(metadata)] = metadata

    label = make_jpeg_fixture(992, 1040, b"label")
    macro = make_jpeg_fixture(1872, 1040, b"macro")
    tile_0 = make_jpeg_fixture(672, 672, b"tile0")
    tile_1 = make_jpeg_fixture(672, 672, b"tile1")
    tile_2 = make_jpeg_fixture(672, 672, b"tile2")
    data[7855:7855 + len(label)] = label
    data[8000:8000 + len(macro)] = macro
    data[8200:8200 + len(tile_0)] = tile_0
    data[8300:8300 + len(tile_1)] = tile_1
    data[8400:8400 + len(tile_2)] = tile_2
    data[8600:8604] = b"\xff\xd8\xffn"

    path.write_bytes(data)


def make_adjacent_tile_length_table_fixture(path: Path) -> dict[str, object]:
    data = bytearray(12000)
    data[:12] = b"SQ1.1.9.0430"
    struct.pack_into("<I", data, 0x12, 156)
    struct.pack_into("<I", data, 0x16, len(data))
    struct.pack_into("<I", data, 0x26, 4)
    struct.pack_into("<I", data, 0x2A, 26880)
    struct.pack_into("<I", data, 0x2E, 21504)
    struct.pack_into("<I", data, 0x32, 672)
    struct.pack_into("<I", data, 0x36, 672)
    struct.pack_into("<I", data, 0x3A, 302)
    struct.pack_into("<I", data, 0x3E, 241)
    struct.pack_into("<f", data, 0x48, 0.25)
    struct.pack_into("<d", data, 0x4C, 0.104538690)
    struct.pack_into("<I", data, 0x54, 40)
    struct.pack_into("<I", data, 0x58, 0x1B34)

    metadata = (
        b"EI\x00\x03\x00\x00\x00\x00"
        b"FV-025GN-X1C\x00"
        b"2022/5/14 14:58:34\x00"
        b"SQS120P-20220006\x00"
        b"UPlanApo40X\x00"
    )
    data[0x1B34:0x1B34 + len(metadata)] = metadata

    label = make_jpeg_fixture(992, 1040, b"label-associated")
    macro = make_jpeg_fixture(1872, 1040, b"macro")
    tiles = [
        make_jpeg_fixture(672, 672, b"t0"),
        make_jpeg_fixture(672, 672, b"tile-one"),
        make_jpeg_fixture(672, 672, b"tile-two-long"),
    ]

    label_offset = 8000
    macro_offset = 8100
    length_table_offset = 8300
    first_tile_offset = 8400
    data[label_offset:label_offset + len(label)] = label
    data[macro_offset:macro_offset + len(macro)] = macro

    tile_offsets: list[int] = []
    cursor = first_tile_offset
    for tile in tiles:
        tile_offsets.append(cursor)
        data[cursor:cursor + len(tile)] = tile
        cursor += len(tile)

    tile_lengths = [len(tile) for tile in tiles]
    data[length_table_offset:length_table_offset + 4 * len(tile_lengths)] = (
        b"".join(struct.pack("<I", value) for value in tile_lengths)
    )

    path.write_bytes(data)
    return {
        "length_table_offset": length_table_offset,
        "first_tile_offset": first_tile_offset,
        "tile_offsets": tile_offsets,
        "tile_end_offsets": [
            offset + length for offset, length in zip(tile_offsets, tile_lengths)
        ],
        "tile_lengths": tile_lengths,
    }
