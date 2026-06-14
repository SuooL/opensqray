from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from opensqray.cli import main as cli_main
from opensqray.sdpc import (
    SDPC_METADATA_SCHEMA_VERSION,
    SDPCFormatError,
    extract_sdpc_associated_images,
    read_sdpc,
)


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


class SDPCParserTests(unittest.TestCase):
    def test_reads_core_header_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)

            info = read_sdpc(path)

        self.assertEqual(info.version, "SQ1.1.9.0430")
        self.assertEqual(info.file_size, 12000)
        self.assertTrue(info.file_size_matches_header)
        self.assertEqual(info.header_size, 156)
        self.assertEqual(info.level_count, 4)
        self.assertEqual(info.dimensions, (26880, 21504))
        self.assertEqual(info.tile_size, (672, 672))
        self.assertEqual(info.thumbnail_size, (302, 241))
        self.assertEqual(info.scan_magnification, 40)
        self.assertEqual(info.metadata["device_id"], "FV-025GN-X1C")
        self.assertEqual(info.metadata["acquired_at"], "2022/5/14 14:58:34")
        self.assertEqual(info.metadata["scanner_model"], "SQS120P-20220006")
        self.assertEqual(info.metadata["objective"], "UPlanApo40X")
        self.assertEqual(
            info.jpeg_streams["offsets_preview"],
            [7855, 8000, 8200, 8300, 8400],
        )
        self.assertEqual(info.jpeg_streams["count"], 5)
        self.assertEqual(
            info.jpeg_streams["records_preview"][0]["dimensions"],
            {"width": 992, "height": 1040},
        )
        self.assertEqual(info.associated_images["count"], 2)
        self.assertEqual(
            [record["name"] for record in info.associated_images["records"]],
            ["label_candidate", "macro_candidate"],
        )
        self.assertEqual(info.tile_index["status"], "candidate")
        self.assertEqual(
            [
                (tile["level"], tile["tile_x"], tile["tile_y"])
                for tile in info.tile_index["tiles_preview"]
            ],
            [(0, 0, 0), (0, 1, 0), (0, 2, 0)],
        )
        self.assertEqual(
            info.tile_index["levels"][0]["grid"],
            {"columns": 40, "rows": 32},
        )
        self.assertEqual(info.tile_index["missing_tiles_preview"][0]["tile_x"], 3)

        payload = info.to_dict()
        self.assertEqual(payload["schema_version"], SDPC_METADATA_SCHEMA_VERSION)
        self.assertEqual(payload["field_confidence"]["dimensions"], "high")
        self.assertEqual(payload["validation"]["warnings"], [])

    def test_counts_jpeg_records_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)

            info = read_sdpc(path, scan_jpegs=True)

        self.assertEqual(info.jpeg_streams["count"], 5)
        self.assertNotIn(8600, info.jpeg_streams["offsets_preview"])

    def test_reports_file_size_mismatch_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path, stored_file_size=8999)

            payload = read_sdpc(path).to_dict()

        self.assertFalse(payload["file_size_matches_header"])
        self.assertEqual(
            payload["validation"]["warnings"],
            [
                {
                    "code": "file_size_mismatch",
                    "message": (
                        "stored_file_size does not match the actual file size"
                    ),
                    "stored_file_size": 8999,
                    "actual_file_size": 12000,
                }
            ],
        )

    def test_rejects_non_sdpc_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "not-sdpc.bin"
            path.write_bytes(b"not an sdpc file")

            with self.assertRaises(SDPCFormatError):
                read_sdpc(path)

    def test_cli_emits_compact_sdpc_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["inspect", str(path), "--compact"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["format"], "sdpc")
        self.assertEqual(payload["schema_version"], SDPC_METADATA_SCHEMA_VERSION)
        self.assertEqual(payload["dimensions"], {"height": 21504, "width": 26880})
        self.assertIn("field_confidence", payload)
        self.assertIn("validation", payload)
        self.assertEqual(payload["associated_images"]["count"], 2)
        self.assertEqual(payload["tile_index"]["status"], "candidate")

    def test_extracts_associated_images_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            output_dir = Path(tmp_dir) / "associated"
            make_sdpc_fixture(path)

            extracted = extract_sdpc_associated_images(path, output_dir)

            self.assertEqual(len(extracted), 2)
            first = Path(extracted[0]["output_path"])
            self.assertTrue(first.exists())
            self.assertEqual(first.read_bytes(), make_jpeg_fixture(992, 1040, b"label"))
            with self.assertRaises(FileExistsError):
                extract_sdpc_associated_images(path, output_dir)

    def test_cli_lists_associated_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["associated", str(path), "--compact"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["records"][1]["name"], "macro_candidate")

    def test_cli_extracts_associated_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            output_dir = Path(tmp_dir) / "associated"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "extract-associated",
                        str(path),
                        "--output-dir",
                        str(output_dir),
                        "--compact",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["extracted_count"], 2)
            self.assertTrue(Path(payload["extracted"][0]["output_path"]).exists())

    def test_cli_lists_tile_index_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["tile-index", str(path), "--compact"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "candidate")
        self.assertEqual(payload["tiles_preview"][1]["tile_x"], 1)
        self.assertEqual(payload["tiles_preview"][1]["tile_y"], 0)
        self.assertEqual(payload["missing_tile_count"], 1697)


if __name__ == "__main__":
    unittest.main()
