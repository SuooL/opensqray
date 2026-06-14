from __future__ import annotations

import unittest
from unittest.mock import patch

from opensqray import ImageDecodeUnavailable, decode_jpeg_bytes

from synthetic_sdpc import make_jpeg_fixture


class FakeImage:
    def __init__(self) -> None:
        self.loaded = False

    def load(self) -> None:
        self.loaded = True


class FakePillowImageModule:
    def __init__(self) -> None:
        self.image = FakeImage()
        self.opened_bytes = b""

    def open(self, stream: object) -> FakeImage:
        self.opened_bytes = stream.read()
        return self.image


class ImageAdapterTests(unittest.TestCase):
    def test_decodes_jpeg_bytes_with_lazy_pillow_import(self) -> None:
        fake_module = FakePillowImageModule()
        jpeg = make_jpeg_fixture(12, 8, b"pixels")

        with patch(
            "opensqray.image_adapter.importlib.import_module",
            return_value=fake_module,
        ) as import_module:
            image = decode_jpeg_bytes(jpeg)

        import_module.assert_called_once_with("PIL.Image")
        self.assertIs(image, fake_module.image)
        self.assertTrue(fake_module.image.loaded)
        self.assertEqual(fake_module.opened_bytes, jpeg)

    def test_reports_missing_pillow_dependency(self) -> None:
        with patch(
            "opensqray.image_adapter.importlib.import_module",
            side_effect=ImportError("missing"),
        ):
            with self.assertRaisesRegex(ImageDecodeUnavailable, "Pillow"):
                decode_jpeg_bytes(b"not decoded")


if __name__ == "__main__":
    unittest.main()
