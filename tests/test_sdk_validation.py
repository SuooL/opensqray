from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from opensqray import (
    OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
    validate_sdk_runtime,
)


class FakeImage:
    def __init__(self, size: tuple[int, int], seed: bytes, mode: str = "RGBA") -> None:
        self.size = size
        self.mode = mode
        self._seed = seed

    def tobytes(self) -> bytes:
        width, height = self.size
        repeats = max(1, width * height * 4 // max(1, len(self._seed)))
        return (self._seed * repeats)[: width * height * 4]

    def getextrema(self):
        data = self.tobytes()
        return tuple((min(data[index::4]), max(data[index::4])) for index in range(4))


class FakeSDKHandle:
    def level_tile_count(self, level: int) -> tuple[int, int]:
        return (4 // (level + 1), 3 // (level + 1))


class FakeValidationSlide:
    def __init__(self, path, *, sdk_dir=None, sdk_lib_dir=None):
        self.path = Path(path)
        self.sdk_dir = sdk_dir
        self.sdk_lib_dir = sdk_lib_dir
        self._sdk_slide = FakeSDKHandle()

    def __enter__(self) -> FakeValidationSlide:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        return None

    @property
    def dimensions(self) -> tuple[int, int]:
        return (1024, 768)

    @property
    def level_count(self) -> int:
        return 2

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return ((1024, 768), (256, 192))

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return (1.0, 4.0)

    @property
    def properties(self) -> dict[str, str]:
        return {
            "openslide.vendor": "sqray",
            "opensqray.backend": "sdk",
            "opensqray.format": "sdpc",
            "opensqray.schema_version": "opensqray.sdpc.metadata.v1",
        }

    @property
    def associated_images(self) -> dict[str, FakeImage]:
        return {
            "thumbnail": FakeImage((128, 96), b"thumbnail"),
            "label": FakeImage((64, 64), b"label"),
        }

    def get_thumbnail(self, size: tuple[int, int]) -> FakeImage:
        return FakeImage((min(size[0], 128), min(size[1], 96)), b"thumb")

    def read_tile_jpeg_bytes(self, *, level: int, tile_x: int, tile_y: int) -> bytes:
        return b"\xff\xd8" + bytes([level, tile_x, tile_y]) + b"\xff\xd9"

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> FakeImage:
        seed = f"{location}:{level}:{size}".encode("ascii")
        return FakeImage(size, seed)


class SDKValidationTests(unittest.TestCase):
    def test_validates_geometry_tiles_regions_and_parallel_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.sdpc"
            path.write_bytes(b"SQ fake")

            payload = validate_sdk_runtime(
                path,
                workers=2,
                patch_size=64,
                patch_count=4,
                repeat_count=2,
                slide_factory=FakeValidationSlide,
            )

        self.assertEqual(
            payload["schema_version"],
            OPENSQRAY_SDK_VALIDATION_SCHEMA_VERSION,
        )
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["checks"]["geometry"]["level_count"], 2)
        self.assertEqual(payload["checks"]["associated_images"]["count"], 2)
        self.assertGreaterEqual(payload["checks"]["tile_jpegs"]["count"], 1)
        self.assertTrue(
            payload["checks"]["parallel_regions"]["consistency"]["matches"]
        )
        self.assertGreater(
            payload["checks"]["performance"]["regions_per_second"],
            0,
        )

    def test_rejects_invalid_validation_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "workers"):
            validate_sdk_runtime(
                "sample.sdpc",
                workers=0,
                slide_factory=FakeValidationSlide,
            )


if __name__ == "__main__":
    unittest.main()
