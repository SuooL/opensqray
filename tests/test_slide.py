from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from opensqray import SDPC_METADATA_SCHEMA_VERSION, SDPCSlide

from synthetic_sdpc import make_jpeg_fixture, make_sdpc_fixture


class SDPCSlideTests(unittest.TestCase):
    def test_exposes_openslide_like_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)

            with SDPCSlide(path) as slide:
                dimensions = slide.dimensions
                level_count = slide.level_count
                level_dimensions = slide.level_dimensions
                level_downsamples = slide.level_downsamples
                properties = slide.properties

        self.assertEqual(dimensions, (26880, 21504))
        self.assertEqual(level_count, 4)
        self.assertEqual(
            level_dimensions,
            (
                (26880, 21504),
                (13440, 10752),
                (6720, 5376),
                (3360, 2688),
            ),
        )
        self.assertEqual(level_downsamples, (1.0, 2.0, 4.0, 8.0))
        self.assertEqual(
            properties["opensqray.schema_version"],
            SDPC_METADATA_SCHEMA_VERSION,
        )
        self.assertEqual(properties["opensqray.sdpc.version"], "SQ1.1.9.0430")
        self.assertEqual(
            properties["opensqray.sdpc.metadata.scanner_model"],
            "SQS120P-20220006",
        )
        self.assertEqual(properties["opensqray.sdpc.tile_index.status"], "candidate")

    def test_reads_associated_and_tile_jpeg_candidate_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)

            slide = SDPCSlide(path)
            associated_names = sorted(slide.associated_images)
            label_bytes = slide.read_associated_image_bytes("label_candidate")
            tile_by_coordinate = slide.read_tile_jpeg_bytes(
                level=0,
                tile_x=1,
                tile_y=0,
            )
            tile_by_sequence = slide.read_tile_jpeg_bytes_by_sequence(2)

        self.assertEqual(associated_names, ["label_candidate", "macro_candidate"])
        self.assertEqual(label_bytes, make_jpeg_fixture(992, 1040, b"label"))
        self.assertEqual(tile_by_coordinate, make_jpeg_fixture(672, 672, b"tile1"))
        self.assertEqual(tile_by_sequence, make_jpeg_fixture(672, 672, b"tile2"))

    def test_missing_candidate_access_raises_clear_key_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            slide = SDPCSlide(path)

            with self.assertRaisesRegex(KeyError, "unknown associated-image"):
                slide.read_associated_image_bytes("thumbnail")
            with self.assertRaisesRegex(KeyError, "current preview"):
                slide.read_tile_jpeg_bytes(level=0, tile_x=10, tile_y=10)

    def test_read_region_is_explicitly_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            slide = SDPCSlide(path)

            with self.assertRaisesRegex(NotImplementedError, "not implemented"):
                slide.read_region((0, 0), 0, (256, 256))

    def test_closed_slide_rejects_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)
            slide = SDPCSlide(path)

            slide.close()

            with self.assertRaisesRegex(ValueError, "closed"):
                _ = slide.dimensions


if __name__ == "__main__":
    unittest.main()
