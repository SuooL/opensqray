from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from opensqray import (
    SDPC_INDEX_RESEARCH_SCHEMA_VERSION,
    scan_sdpc_index_research,
)
from opensqray.cli import main as cli_main

from synthetic_sdpc import make_sdpc_fixture


def write_uint32_offset_table(
    path: Path,
    offset: int,
    values: list[int],
    *,
    before: bytes = b"",
    after: bytes = b"",
) -> None:
    with path.open("r+b") as handle:
        if before:
            handle.seek(offset - len(before))
            handle.write(before)
        handle.seek(offset)
        handle.write(b"".join(struct.pack("<I", value) for value in values))
        if after:
            handle.write(after)


class SDPCIndexResearchTests(unittest.TestCase):
    def test_finds_packed_jpeg_offset_candidate_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            write_uint32_offset_table(
                path,
                7200,
                [8200, 8300, 8400],
                before=b"ABCD",
                after=b"WXYZ",
            )

            payload = scan_sdpc_index_research(path, context_bytes=4)

        self.assertEqual(
            payload["schema_version"],
            SDPC_INDEX_RESEARCH_SCHEMA_VERSION,
        )
        self.assertEqual(payload["format"], "sdpc")
        self.assertEqual(
            payload["strategy"],
            "packed_known_jpeg_record_fields_in_non_jpeg_windows",
        )
        self.assertGreaterEqual(payload["candidate_table_count"], 1)
        candidate = payload["candidate_tables"][0]
        self.assertEqual(candidate["target"], "offset")
        self.assertEqual(candidate["encoding"], "uint32le")
        self.assertEqual(candidate["window"], "before_first_jpeg")
        self.assertEqual(candidate["window_relative_offset"], 7200)
        self.assertEqual(candidate["offset"], 7200)
        self.assertEqual(candidate["end_offset"], 7212)
        self.assertEqual(candidate["match_count"], 3)
        self.assertEqual(candidate["start_record_index"], 2)
        self.assertEqual(candidate["end_record_index"], 4)
        self.assertEqual(candidate["distance_to_window_end"], 643)
        self.assertEqual(
            candidate["context"],
            {
                "bytes_before": 4,
                "before_hex": b"ABCD".hex(),
                "bytes_after": 4,
                "after_hex": b"WXYZ".hex(),
            },
        )
        self.assertEqual(candidate["values_preview"], [8200, 8300, 8400])
        self.assertEqual(candidate["confidence"], "diagnostic")

    def test_respects_minimum_table_match_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            write_uint32_offset_table(path, 7200, [8200, 8300])

            payload = scan_sdpc_index_research(path, min_table_matches=3)

        self.assertEqual(payload["candidate_table_count"], 0)
        self.assertEqual(payload["candidate_tables"], [])

    def test_cli_runs_index_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            write_uint32_offset_table(path, 7200, [8200, 8300, 8400])
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["index-research", str(path), "--compact"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["schema_version"],
            SDPC_INDEX_RESEARCH_SCHEMA_VERSION,
        )
        self.assertGreaterEqual(payload["candidate_table_count"], 1)

    def test_cli_rejects_invalid_research_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "index-research",
                        str(path),
                        "--min-table-matches",
                        "0",
                        "--context-bytes",
                        "16",
                    ]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--min-table-matches must be positive", stderr.getvalue())

    def test_cli_rejects_negative_context_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "index-research",
                        str(path),
                        "--context-bytes",
                        "-1",
                    ]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--context-bytes must be non-negative", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
