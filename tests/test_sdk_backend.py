from __future__ import annotations

import ctypes
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opensqray.sdk_backend import (
    SqraySDKSlide,
    SqraySDKUnavailable,
    inspect_sqray_sdk_slide,
)


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeSqrayLibrary:
    def __init__(self, *, open_ok: bool = True) -> None:
        self.open_ok = open_ok
        self.closed = False
        self.freed = False
        self.buffers: list[ctypes.Array[ctypes.c_ubyte]] = []
        self.sqrayslide_open = FakeFunction(self._open)
        self.sqrayslide_close = FakeFunction(self._close)
        self.sqrayslide_free_memory = FakeFunction(self._free_memory)
        self.sqrayslide_get_tile_size = FakeFunction(self._get_tile_size)
        self.sqrayslide_get_level_count = FakeFunction(self._get_level_count)
        self.sqrayslide_get_level_size = FakeFunction(self._get_level_size)
        self.sqrayslide_get_level_tile_count = FakeFunction(
            self._get_level_tile_count
        )
        self.sqrayslide_read_tile_jpeg = FakeFunction(self._read_tile_jpeg)
        self.sqrayslide_read_region_bgra = FakeFunction(self._read_region_bgra)

    def _open(self, path, status_ptr):
        status_ptr._obj.value = 0 if self.open_ok else -1
        return ctypes.c_void_p(1234) if self.open_ok else None

    def _close(self, handle):
        self.closed = True

    def _free_memory(self, data_ptr):
        self.freed = True

    def _get_tile_size(self, handle, width_ptr, height_ptr):
        width_ptr._obj.value = 544
        height_ptr._obj.value = 448

    def _get_level_count(self, handle):
        return 2

    def _get_level_size(self, handle, level, width_ptr, height_ptr):
        width_ptr._obj.value = 50048 // (2 ** level)
        height_ptr._obj.value = 93184 // (2 ** level)

    def _get_level_tile_count(self, handle, level, columns_ptr, rows_ptr):
        columns_ptr._obj.value = 92 // (2 ** level)
        rows_ptr._obj.value = 208 // (2 ** level)

    def _read_tile_jpeg(self, handle, dest_ptr, tile_x, tile_y, level):
        data = bytes([0xFF, 0xD8, level, tile_x, tile_y, 0xFF, 0xD9])
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        self.buffers.append(buffer)
        dest_ptr._obj.value = ctypes.cast(buffer, ctypes.c_void_p).value
        return len(data)

    def _read_region_bgra(self, handle, dest, x, y, width, height, level):
        for index in range(width * height * 4):
            dest[index] = index % 256
        return True


class SqraySDKBackendTests(unittest.TestCase):
    def test_reports_missing_sdk_configuration(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(SqraySDKUnavailable, "not configured"):
                SqraySDKSlide("sample.sdpc")

    def test_reads_sdk_geometry_tile_jpeg_and_region_bytes(self) -> None:
        fake_library = FakeSqrayLibrary()

        slide = SqraySDKSlide("sample.sdpc", _library=fake_library)
        tile_bytes = slide.read_tile_jpeg_bytes(level=0, tile_x=1, tile_y=2)
        region_bytes = slide.read_region_bgra_bytes(
            location=(0, 0),
            level=0,
            size=(2, 2),
        )
        tile_size = slide.tile_size
        level_count = slide.level_count
        level_size = slide.level_size(0)
        level_tile_count = slide.level_tile_count(0)
        slide.close()

        self.assertEqual(tile_bytes, b"\xff\xd8\x00\x01\x02\xff\xd9")
        self.assertTrue(fake_library.freed)
        self.assertEqual(region_bytes, bytes(range(16)))
        self.assertEqual(tile_size, (544, 448))
        self.assertEqual(level_count, 2)
        self.assertEqual(level_size, (50048, 93184))
        self.assertEqual(level_tile_count, (92, 208))
        self.assertTrue(fake_library.closed)

    def test_rejects_failed_open(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "failed to open"):
            SqraySDKSlide("sample.sdpc", _library=FakeSqrayLibrary(open_ok=False))

    def test_inspects_sdk_slide_geometry(self) -> None:
        fake_library = FakeSqrayLibrary()

        with patch(
            "opensqray.sdk_backend.SqraySDKSlide",
            return_value=SqraySDKSlide("sample.sdpc", _library=fake_library),
        ):
            payload = inspect_sqray_sdk_slide("sample.sdpc")

        self.assertEqual(payload["backend"], "sqray_sdk")
        self.assertEqual(payload["tile_size"], {"width": 544, "height": 448})
        self.assertEqual(payload["level_count"], 2)
        self.assertEqual(
            payload["levels"][0]["tile_grid"],
            {"columns": 92, "rows": 208},
        )


if __name__ == "__main__":
    unittest.main()
