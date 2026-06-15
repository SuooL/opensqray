from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from opensqray import (
    RegionRequest,
    iter_regions,
    iter_patch_requests,
    read_regions,
    recommended_worker_count,
)


class FakeSlide:
    opened_paths: list[Path] = []

    def __init__(self, path, *, sdk_dir=None, sdk_lib_dir=None):
        self.path = Path(path)
        self.sdk_dir = sdk_dir
        self.sdk_lib_dir = sdk_lib_dir
        self.closed = False
        FakeSlide.opened_paths.append(self.path)

    def __enter__(self) -> FakeSlide:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True

    def read_region(self, location, level, size):
        return {
            "path": str(self.path),
            "location": location,
            "level": level,
            "size": size,
            "sdk_dir": self.sdk_dir,
            "sdk_lib_dir": self.sdk_lib_dir,
        }


class BatchReadTests(unittest.TestCase):
    def test_iter_patch_requests_yields_level_zero_grid(self) -> None:
        requests = list(iter_patch_requests((10, 8), (4, 3), stride=(4, 3)))

        self.assertEqual(
            requests,
            [
                RegionRequest((0, 0), 0, (4, 3), key=(0, 0)),
                RegionRequest((4, 0), 0, (4, 3), key=(4, 0)),
                RegionRequest((0, 3), 0, (4, 3), key=(0, 3)),
                RegionRequest((4, 3), 0, (4, 3), key=(4, 3)),
            ],
        )

    def test_iter_patch_requests_can_include_partial_edges(self) -> None:
        requests = list(
            iter_patch_requests(
                (5, 5),
                3,
                stride=3,
                include_partial=True,
            )
        )

        self.assertEqual(
            [request.size for request in requests],
            [(3, 3), (2, 3), (3, 2), (2, 2)],
        )

    def test_read_regions_preserves_request_order_with_parallel_workers(self) -> None:
        FakeSlide.opened_paths = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "slide.sdpc"
            requests = [
                RegionRequest((20, 0), 0, (2, 2)),
                ((0, 0), 0, (1, 1)),
                RegionRequest((10, 0), 1, (3, 3)),
            ]

            images = read_regions(
                path,
                requests,
                workers=2,
                sdk_dir="sdk-root",
                sdk_lib_dir="sdk-lib",
                slide_factory=FakeSlide,
            )

        self.assertEqual(
            [image["location"] for image in images],
            [(20, 0), (0, 0), (10, 0)],
        )
        self.assertEqual({image["sdk_dir"] for image in images}, {"sdk-root"})
        self.assertEqual({image["sdk_lib_dir"] for image in images}, {"sdk-lib"})
        self.assertEqual(len(FakeSlide.opened_paths), 2)

    def test_read_regions_rejects_invalid_workers(self) -> None:
        with self.assertRaisesRegex(ValueError, "workers"):
            read_regions("slide.sdpc", [], workers=0, slide_factory=FakeSlide)

    def test_iter_regions_streams_chunks_and_preserves_keys(self) -> None:
        FakeSlide.opened_paths = []
        requests = (
            RegionRequest((index, 0), 0, (1, 1), key=f"patch-{index}")
            for index in range(5)
        )

        results = list(
            iter_regions(
                "slide.sdpc",
                requests,
                workers=2,
                chunk_size=2,
                slide_factory=FakeSlide,
            )
        )

        self.assertEqual([result.key for result in results], [
            "patch-0",
            "patch-1",
            "patch-2",
            "patch-3",
            "patch-4",
        ])
        self.assertEqual(
            [result.image["location"] for result in results],
            [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],
        )
        self.assertEqual(len(FakeSlide.opened_paths), 5)

    def test_iter_regions_rejects_invalid_chunk_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "chunk_size"):
            list(iter_regions("slide.sdpc", [], chunk_size=0, slide_factory=FakeSlide))

    def test_recommended_worker_count_is_bounded(self) -> None:
        self.assertEqual(recommended_worker_count(slide_count=1, max_workers=1), 1)
        self.assertGreaterEqual(
            recommended_worker_count(slide_count=4, max_workers=4),
            1,
        )


if __name__ == "__main__":
    unittest.main()
