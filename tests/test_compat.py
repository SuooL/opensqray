from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opensqray import OpenSqraySlide, is_sdpc
from opensqray.compat import (
    PROPERTY_NAME_MPP_X,
    PROPERTY_NAME_OBJECTIVE_POWER,
    PROPERTY_NAME_VENDOR,
)

from synthetic_sdpc import make_sdpc_fixture


class FakeImage:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self.loaded = False

    def copy(self) -> FakeImage:
        return FakeImage(self.size)

    def thumbnail(self, size: tuple[int, int]) -> None:
        self.size = size

    def load(self) -> None:
        self.loaded = True


class FakeSDKSlide:
    def __init__(self, path, *, sdk_dir=None, lib_dir=None):
        self.path = path
        self.closed = False
        self.region_requests = []

    def close(self) -> None:
        self.closed = True

    @property
    def tile_size(self):
        return (672, 672)

    @property
    def level_count(self):
        return 3

    @property
    def mpp(self):
        return (0.25, 0.25)

    @property
    def magnification(self):
        return 40.0

    @property
    def barcode(self):
        return "barcode-1"

    def level_size(self, level):
        return [(26880, 21504), (6720, 5376), (2016, 1344)][level]

    def level_downsample(self, level):
        return [1.0, 4.0, 13.3333333333][level]

    def best_level_for_downsample(self, downsample):
        return 1 if downsample >= 4 else 0

    def read_associated_jpeg_bytes(self, name):
        sizes = {
            "label": (992, 1040),
            "thumbnail": (302, 241),
            "macro": (1872, 1040),
        }
        return sizes[name], f"jpeg:{name}".encode("ascii")

    def read_region_bgra_bytes(self, *, location, level, size):
        self.region_requests.append((location, level, size))
        return b"bgra" * (size[0] * size[1])

    def read_tile_jpeg_bytes(self, *, level, tile_x, tile_y):
        return f"tile:{level}:{tile_x}:{tile_y}".encode("ascii")


class OpenSqraySlideCompatTests(unittest.TestCase):
    def test_sdpc_signature_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sdpc_path = Path(tmp_dir) / "sample.sdpc"
            other_path = Path(tmp_dir) / "sample.txt"
            make_sdpc_fixture(sdpc_path)
            other_path.write_bytes(b"not sdpc")

            self.assertTrue(is_sdpc(sdpc_path))
            self.assertFalse(is_sdpc(other_path))

    def test_openslide_like_core_api_uses_sdk_backend(self) -> None:
        decoded_images: list[bytes] = []

        def fake_decode(data: bytes) -> FakeImage:
            decoded_images.append(data)
            if data == b"jpeg:thumbnail":
                return FakeImage((302, 241))
            return FakeImage((100, 100))

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            make_sdpc_fixture(path)

            with patch("opensqray.compat.SqraySDKSlide", FakeSDKSlide), patch(
                "opensqray.compat.decode_jpeg_bytes",
                side_effect=fake_decode,
            ), patch(
                "opensqray.compat.image_from_bgra_bytes",
                return_value="region-image",
            ) as image_from_bgra:
                with OpenSqraySlide(path) as slide:
                    dimensions = slide.dimensions
                    level_count = slide.level_count
                    level_dimensions = slide.level_dimensions
                    level_downsamples = slide.level_downsamples
                    properties = slide.properties
                    associated = slide.associated_images
                    region = slide.read_region((10, 20), 1, (2, 3))
                    regions = slide.read_regions(
                        [
                            ((0, 0), 0, (1, 1)),
                            ((2, 3), 1, (2, 2)),
                        ]
                    )
                    thumbnail = slide.get_thumbnail((128, 128))
                    best_level = slide.get_best_level_for_downsample(4)
                    tile = slide.read_tile_jpeg_bytes(level=0, tile_x=1, tile_y=2)
                closed = slide._sdk_slide.closed

        self.assertEqual(dimensions, (26880, 21504))
        self.assertEqual(level_count, 3)
        self.assertEqual(
            level_dimensions,
            ((26880, 21504), (6720, 5376), (2016, 1344)),
        )
        self.assertEqual(level_downsamples, (1.0, 4.0, 16.0))
        self.assertEqual(properties[PROPERTY_NAME_VENDOR], "sqray")
        self.assertEqual(properties[PROPERTY_NAME_OBJECTIVE_POWER], "40")
        self.assertEqual(properties[PROPERTY_NAME_MPP_X], "0.25")
        self.assertEqual(properties["opensqray.backend"], "sdk")
        self.assertEqual(sorted(associated), ["label", "macro", "thumbnail"])
        self.assertEqual(image_from_bgra.call_count, 3)
        self.assertEqual(
            image_from_bgra.call_args_list[0].args,
            (b"bgra" * 6, (2, 3)),
        )
        self.assertEqual(image_from_bgra.call_args_list[1].args, (b"bgra", (1, 1)))
        self.assertEqual(
            image_from_bgra.call_args_list[2].args,
            (b"bgra" * 4, (2, 2)),
        )
        self.assertEqual(region, "region-image")
        self.assertEqual(regions, ["region-image", "region-image"])
        self.assertEqual(thumbnail.size, (128, 128))
        self.assertEqual(best_level, 1)
        self.assertEqual(tile, b"tile:0:1:2")
        self.assertEqual(
            slide._sdk_slide.region_requests,
            [
                ((2, 5), 1, (2, 3)),
                ((0, 0), 0, (1, 1)),
                ((0, 0), 1, (2, 2)),
            ],
        )
        self.assertIn(b"jpeg:thumbnail", decoded_images)
        self.assertTrue(closed)


if __name__ == "__main__":
    unittest.main()
