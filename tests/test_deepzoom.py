from __future__ import annotations

import unittest

from opensqray import OpenSqrayDeepZoomGenerator


class FakeImage:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self.resized_to: tuple[int, int] | None = None

    def resize(self, size: tuple[int, int]) -> FakeImage:
        image = FakeImage(size)
        image.resized_to = size
        return image


class FakeSlide:
    dimensions = (1000, 800)
    level_downsamples = (1.0, 4.0)

    def __init__(self) -> None:
        self.region_requests: list[tuple[tuple[int, int], int, tuple[int, int]]] = []

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return 1 if downsample >= 4 else 0

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> FakeImage:
        self.region_requests.append((location, level, size))
        return FakeImage(size)


class OpenSqrayDeepZoomGeneratorTests(unittest.TestCase):
    def test_reports_deepzoom_levels_and_tile_count(self) -> None:
        generator = OpenSqrayDeepZoomGenerator(
            FakeSlide(),
            tile_size=254,
            overlap=1,
        )

        self.assertEqual(generator.level_count, 11)
        self.assertEqual(generator.level_dimensions[0], (1, 1))
        self.assertEqual(generator.level_dimensions[-1], (1000, 800))
        self.assertEqual(generator.level_tiles[-1], (4, 4))
        self.assertGreater(generator.tile_count, 0)

    def test_get_tile_coordinates_use_level_zero_location(self) -> None:
        slide = FakeSlide()
        generator = OpenSqrayDeepZoomGenerator(slide, tile_size=254, overlap=1)

        coordinates = generator.get_tile_coordinates(10, (1, 1))
        tile = generator.get_tile(10, (1, 1))

        self.assertEqual(coordinates, ((253, 253), 0, (256, 256)))
        self.assertEqual(slide.region_requests, [((253, 253), 0, (256, 256))])
        self.assertEqual(tile.size, (256, 256))

    def test_edge_tile_dimensions_are_clipped_to_slide_bounds(self) -> None:
        generator = OpenSqrayDeepZoomGenerator(FakeSlide(), tile_size=254, overlap=1)

        self.assertEqual(generator.get_tile_dimensions(10, (3, 3)), (239, 39))

    def test_low_resolution_tile_uses_best_slide_level_and_resizes(self) -> None:
        slide = FakeSlide()
        generator = OpenSqrayDeepZoomGenerator(slide, tile_size=254, overlap=0)

        tile = generator.get_tile(7, (0, 0))

        self.assertEqual(slide.region_requests, [((0, 0), 1, (250, 200))])
        self.assertEqual(tile.size, (125, 100))
        self.assertEqual(tile.resized_to, (125, 100))

    def test_dzi_descriptor_uses_level_zero_dimensions(self) -> None:
        generator = OpenSqrayDeepZoomGenerator(FakeSlide())

        self.assertEqual(
            generator.get_dzi("jpeg"),
            '<Image TileSize="254" Overlap="1" Format="jpeg" '
            'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
            '<Size Width="1000" Height="800"/></Image>',
        )

    def test_rejects_out_of_range_tile(self) -> None:
        generator = OpenSqrayDeepZoomGenerator(FakeSlide())

        with self.assertRaisesRegex(ValueError, "tile address out of range"):
            generator.get_tile_dimensions(10, (4, 0))


if __name__ == "__main__":
    unittest.main()
