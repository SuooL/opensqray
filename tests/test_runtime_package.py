from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from opensqray import (
    RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION,
    check_runtime_package_layout,
)


class RuntimePackageCheckTests(unittest.TestCase):
    def test_accepts_linux_runtime_package_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            lib_dir = root / "linux-x86_64" / "lib"
            lib_dir.mkdir(parents=True)
            (lib_dir / "libsqrayslideservice.so").touch()

            payload = check_runtime_package_layout(root, platform_tag="linux-x86_64")

        self.assertEqual(
            payload["schema_version"],
            RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION,
        )
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["service_library_name"], "libsqrayslideservice.so")

    def test_accepts_windows_runtime_package_bin_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bin_dir = root / "windows-x86_64" / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "sqrayslideservice.dll").touch()

            payload = check_runtime_package_layout(
                root,
                platform_tag="windows-x86_64",
            )

        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["service_library_name"], "sqrayslideservice.dll")
        self.assertEqual(payload["existing_library_dirs"], [str(bin_dir)])

    def test_reports_missing_service_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "macos-arm64" / "lib").mkdir(parents=True)

            payload = check_runtime_package_layout(root, platform_tag="macos-arm64")

        self.assertEqual(payload["status"], "failed")
        self.assertIn("service library", payload["errors"][0])

    def test_warns_about_linux_duplicate_library_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            lib_dir = root / "linux-x86_64" / "lib"
            lib_dir.mkdir(parents=True)
            (lib_dir / "libsqrayslideservice.so").touch()
            (lib_dir / "libavcodec.so").touch()
            (lib_dir / "libavcodec.so.58").touch()

            payload = check_runtime_package_layout(root, platform_tag="linux-x86_64")

        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["warnings"])


if __name__ == "__main__":
    unittest.main()
