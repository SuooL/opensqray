from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from opensqray import (
    RUNTIME_WHEEL_BUILD_SCHEMA_VERSION,
    RUNTIME_PACKAGE_MANIFEST_NAME,
    RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION,
    RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION,
    build_runtime_wheel,
    check_runtime_package_layout,
    stage_runtime_package_layout,
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

    def test_stages_linux_runtime_package_without_duplicate_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            output = Path(tmp_dir) / "runtime"
            source.mkdir()
            for name in (
                "libsqrayslideservice.so",
                "libavcodec.so",
                "libavcodec.so.58",
                "libavcodec.so.58.111.100",
                "libavutil.so.56",
                "libsqrayslidebase.so",
            ):
                (source / name).write_bytes(name.encode("ascii"))

            payload = stage_runtime_package_layout(
                source,
                output,
                platform_tag="linux-x86_64",
            )

            staged_lib = output / "linux-x86_64" / "lib"
            staged_names = sorted(path.name for path in staged_lib.iterdir())
            manifest_path = output / RUNTIME_PACKAGE_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["schema_version"],
            RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION,
        )
        self.assertEqual(payload["status"], "passed")
        self.assertIn("libsqrayslideservice.so", staged_names)
        self.assertIn("libavcodec.so.58", staged_names)
        self.assertNotIn("libavcodec.so", staged_names)
        self.assertNotIn("libavcodec.so.58.111.100", staged_names)
        self.assertEqual(payload["manifest"], str(manifest_path))
        self.assertEqual(
            manifest["schema_version"],
            RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION,
        )
        self.assertEqual(manifest["platform_tag"], "linux-x86_64")
        self.assertEqual(manifest["file_count"], payload["file_count"])
        self.assertEqual(
            sorted(Path(item["destination"]).name for item in manifest["files"]),
            staged_names,
        )

    def test_stage_runtime_package_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            output = Path(tmp_dir) / "runtime"
            source.mkdir()
            (source / "sqrayslideservice.dll").write_bytes(b"dll")

            payload = stage_runtime_package_layout(
                source,
                output,
                platform_tag="windows-x86_64",
                dry_run=True,
            )

        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["dry_run"])
        self.assertFalse(output.exists())

    def test_stage_runtime_package_refuses_to_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            output = Path(tmp_dir) / "runtime"
            source.mkdir()
            (source / "libsqrayslideservice.dylib").write_bytes(b"first")
            stage_runtime_package_layout(
                source,
                output,
                platform_tag="macos-arm64",
            )
            (source / "libsqrayslideservice.dylib").write_bytes(b"second")

            payload = stage_runtime_package_layout(
                source,
                output,
                platform_tag="macos-arm64",
            )

        self.assertEqual(payload["status"], "failed")
        self.assertIn("refusing to overwrite", payload["errors"][0])

    def test_stages_windows_runtime_package_to_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            output = Path(tmp_dir) / "runtime"
            source.mkdir()
            (source / "sqrayslideservice.dll").write_bytes(b"service")
            (source / "dependency.dll").write_bytes(b"dependency")
            (source / "not-a-dll.txt").write_bytes(b"ignore")

            payload = stage_runtime_package_layout(
                source,
                output,
                platform_tag="windows-x86_64",
            )

            staged_bin = output / "windows-x86_64" / "bin"
            staged_names = sorted(path.name for path in staged_bin.iterdir())

        self.assertEqual(payload["status"], "passed")
        self.assertEqual(staged_names, ["dependency.dll", "sqrayslideservice.dll"])

    def test_builds_private_runtime_wheel_without_manifest_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "runtime"
            dist = Path(tmp_dir) / "dist"
            lib_dir = root / "linux-x86_64" / "lib"
            lib_dir.mkdir(parents=True)
            (lib_dir / "libsqrayslideservice.so").write_bytes(b"service")
            (root / RUNTIME_PACKAGE_MANIFEST_NAME).write_text(
                "contains private local paths",
                encoding="utf-8",
            )

            payload = build_runtime_wheel(
                root,
                dist,
                version="0.1.0+test",
                platform_tag="linux-x86_64",
            )
            wheel_path = Path(str(payload["wheel"]))
            with zipfile.ZipFile(wheel_path) as wheel:
                names = sorted(wheel.namelist())
                record = wheel.read(
                    "opensqray_sdk_runtime-0.1.0+test.dist-info/RECORD"
                ).decode("utf-8")

        self.assertEqual(
            payload["schema_version"],
            RUNTIME_WHEEL_BUILD_SCHEMA_VERSION,
        )
        self.assertEqual(payload["status"], "passed")
        self.assertTrue(wheel_path.name.endswith("manylinux_2_17_x86_64.whl"))
        self.assertIn(
            "opensqray_sdk_runtime/linux-x86_64/lib/libsqrayslideservice.so",
            names,
        )
        self.assertIn("opensqray_sdk_runtime/__init__.py", names)
        self.assertIn(
            "opensqray_sdk_runtime-0.1.0+test.dist-info/WHEEL",
            names,
        )
        self.assertNotIn(
            f"opensqray_sdk_runtime/{RUNTIME_PACKAGE_MANIFEST_NAME}",
            names,
        )
        self.assertIn("libsqrayslideservice.so,sha256=", record)

    def test_build_runtime_wheel_refuses_existing_wheel_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "runtime"
            dist = Path(tmp_dir) / "dist"
            lib_dir = root / "macos-arm64" / "lib"
            lib_dir.mkdir(parents=True)
            (lib_dir / "libsqrayslideservice.dylib").write_bytes(b"service")

            build_runtime_wheel(root, dist, platform_tag="macos-arm64")
            payload = build_runtime_wheel(root, dist, platform_tag="macos-arm64")

        self.assertEqual(payload["status"], "failed")
        self.assertIn("refusing to overwrite", payload["errors"][0])


if __name__ == "__main__":
    unittest.main()
