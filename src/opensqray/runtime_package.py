"""Static checks for private Sqray SDK runtime package layouts."""

from __future__ import annotations

from pathlib import Path
import platform


RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION = "opensqray.sdk.runtime_package_check.v1"


def check_runtime_package_layout(
    root: str | Path,
    *,
    platform_tag: str | None = None,
) -> dict[str, object]:
    """Check a private runtime package layout without loading native code."""

    package_root = Path(root)
    tag = platform_tag or _current_platform_tag()
    library_dirs = _candidate_library_dirs(package_root, tag)
    service_name = _service_library_name_for_tag(tag)
    errors: list[str] = []
    warnings: list[str] = []

    if not package_root.exists():
        errors.append(f"runtime package root does not exist: {package_root}")
    elif not package_root.is_dir():
        errors.append(f"runtime package root is not a directory: {package_root}")

    existing_dirs = [path for path in library_dirs if path.is_dir()]
    service_matches = [
        directory / service_name
        for directory in existing_dirs
        if (directory / service_name).is_file()
    ]
    if not existing_dirs:
        errors.append(
            "no platform library directory found; expected one of: "
            + ", ".join(str(path) for path in library_dirs)
        )
    elif not service_matches:
        errors.append(
            f"service library {service_name!r} not found in platform library dirs"
        )

    if tag.startswith("linux-"):
        _warn_for_linux_duplicate_libraries(existing_dirs, warnings)

    return {
        "schema_version": RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION,
        "status": "passed" if not errors else "failed",
        "root": str(package_root),
        "platform_tag": tag,
        "service_library_name": service_name,
        "candidate_library_dirs": [str(path) for path in library_dirs],
        "existing_library_dirs": [str(path) for path in existing_dirs],
        "service_libraries": [str(path) for path in service_matches],
        "errors": errors,
        "warnings": warnings,
    }


def _candidate_library_dirs(root: Path, platform_tag: str) -> list[Path]:
    if platform_tag.startswith("windows-"):
        return [root / platform_tag / "bin", root / platform_tag / "lib"]
    return [root / platform_tag / "lib"]


def _service_library_name_for_tag(platform_tag: str) -> str:
    if platform_tag.startswith("windows-"):
        return "sqrayslideservice.dll"
    if platform_tag.startswith("macos-"):
        return "libsqrayslideservice.dylib"
    return "libsqrayslideservice.so"


def _current_platform_tag() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        arch = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        arch = machine or "unknown"

    if system == "Darwin":
        return f"macos-{arch}"
    if system == "Windows":
        return f"windows-{arch}"
    if system == "Linux":
        return f"linux-{arch}"
    return f"{system.lower() or 'unknown'}-{arch}"


def _warn_for_linux_duplicate_libraries(
    library_dirs: list[Path],
    warnings: list[str],
) -> None:
    for directory in library_dirs:
        for base_name in ("libavcodec", "libavutil", "libswresample"):
            matches = sorted(directory.glob(f"{base_name}.so*"))
            if len(matches) > 1:
                warnings.append(
                    "linux runtime directory contains duplicate shared-library "
                    f"copies for {base_name}; package the minimal needed soname "
                    "set when possible"
                )
