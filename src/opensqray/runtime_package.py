"""Static checks and staging helpers for private Sqray SDK runtimes."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import shutil
import subprocess


RUNTIME_PACKAGE_CHECK_SCHEMA_VERSION = "opensqray.sdk.runtime_package_check.v1"
RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION = "opensqray.sdk.runtime_package_stage.v1"
RUNTIME_PACKAGE_MANIFEST_NAME = "opensqray-sdk-runtime-manifest.json"
_LINUX_RUNTIME_LIBRARY_NAMES = (
    "libsqrayslideservice.so",
    "libavutil.so.56",
    "libswresample.so.3",
    "libx264.so.148",
    "libx265.so.79",
    "libavcodec.so.58",
    "libofstd.so.17",
    "liboflog.so.17",
    "libdcmdata.so.17",
    "libHevc.so",
    "libTJpg.so",
    "libsqrayslidebase.so",
    "libsqrayslidedcm.so",
    "libsqrayslidesdpc.so",
)


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


def stage_runtime_package_layout(
    source_lib_dir: str | Path,
    output_root: str | Path,
    *,
    platform_tag: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Stage SDK runtime libraries into the private runtime package layout."""

    source = Path(source_lib_dir)
    output = Path(output_root)
    tag = platform_tag or _current_platform_tag()
    destination_dir = _candidate_library_dirs(output, tag)[0]
    errors: list[str] = []
    warnings: list[str] = []

    if not source.exists():
        errors.append(f"source library directory does not exist: {source}")
    elif not source.is_dir():
        errors.append(f"source library path is not a directory: {source}")

    files = _stage_source_files(source, tag, warnings) if not errors else []
    service_name = _service_library_name_for_tag(tag)
    if source.is_dir() and not (source / service_name).is_file():
        errors.append(f"service library {service_name!r} not found in {source}")

    missing_recommended = [
        name
        for name in _recommended_library_names(tag)
        if source.is_dir() and not (source / name).is_file()
    ]
    for name in missing_recommended:
        warnings.append(f"recommended runtime library not found: {name}")

    planned_files = [
        {
            "source": str(path),
            "destination": str(destination_dir / path.name),
            "byte_length": path.stat().st_size,
        }
        for path in files
    ]

    if not dry_run and not errors:
        for item in planned_files:
            destination = Path(str(item["destination"]))
            if destination.exists() and not overwrite:
                errors.append(
                    f"refusing to overwrite existing file: {destination}"
                )
        manifest_path = output / RUNTIME_PACKAGE_MANIFEST_NAME
        if manifest_path.exists() and not overwrite:
            errors.append(f"refusing to overwrite existing file: {manifest_path}")

    if not dry_run and not errors:
        destination_dir.mkdir(parents=True, exist_ok=True)
        for path in files:
            destination = destination_dir / path.name
            shutil.copy2(path, destination)
        manifest = _stage_manifest(
            source=source,
            output=output,
            platform_tag=tag,
            files=planned_files,
            warnings=warnings,
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    status = "passed" if not errors else "failed"
    return {
        "schema_version": RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION,
        "status": status,
        "dry_run": dry_run,
        "source_lib_dir": str(source),
        "output_root": str(output),
        "platform_tag": tag,
        "destination_dir": str(destination_dir),
        "file_count": len(planned_files),
        "files": planned_files,
        "manifest": (
            None if dry_run else str(output / RUNTIME_PACKAGE_MANIFEST_NAME)
        ),
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


def _stage_source_files(
    source: Path,
    platform_tag: str,
    warnings: list[str],
) -> list[Path]:
    if platform_tag.startswith("linux-"):
        return [
            source / name
            for name in _LINUX_RUNTIME_LIBRARY_NAMES
            if (source / name).is_file()
        ]
    if platform_tag.startswith("windows-"):
        return sorted(
            path for path in source.iterdir() if path.suffix.lower() == ".dll"
        )
    if platform_tag.startswith("macos-"):
        return _macos_runtime_dependency_closure(source, warnings)
    service = source / _service_library_name_for_tag(platform_tag)
    return [service] if service.is_file() else []


def _recommended_library_names(platform_tag: str) -> tuple[str, ...]:
    if platform_tag.startswith("linux-"):
        return _LINUX_RUNTIME_LIBRARY_NAMES
    return (_service_library_name_for_tag(platform_tag),)


def _stage_manifest(
    *,
    source: Path,
    output: Path,
    platform_tag: str,
    files: list[dict[str, object]],
    warnings: list[str],
) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_PACKAGE_STAGE_SCHEMA_VERSION,
        "source_lib_dir": str(source),
        "output_root": str(output),
        "platform_tag": platform_tag,
        "file_count": len(files),
        "files": files,
        "warnings": warnings,
        "validation_required": (
            "Run tools/validate_sdk_runtime.py on a real SDPC slide before "
            "treating this runtime package as usable."
        ),
    }


def _macos_runtime_dependency_closure(
    source: Path,
    warnings: list[str],
) -> list[Path]:
    service = source / "libsqrayslideservice.dylib"
    if not service.is_file():
        return []

    queue = [service]
    staged: dict[str, Path] = {}
    while queue:
        current = queue.pop(0)
        if current.name in staged:
            continue
        staged[current.name] = current
        dependency_names = _macos_local_dependency_names(current, source)
        if dependency_names is None:
            warnings.append(
                "could not inspect macOS dylib dependencies with otool; "
                "staging all dylibs as a conservative fallback"
            )
            return sorted(path for path in source.iterdir() if path.suffix == ".dylib")
        for name in dependency_names:
            dependency = source / name
            if dependency.is_file() and dependency.name not in staged:
                queue.append(dependency)

    return [staged[name] for name in sorted(staged)]


def _macos_local_dependency_names(
    library: Path,
    source: Path,
) -> set[str] | None:
    try:
        result = subprocess.run(
            ["otool", "-L", str(library)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    names: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        dependency = line.strip().split(" ", 1)[0]
        if not dependency:
            continue
        name = Path(dependency).name
        if name != library.name and (source / name).is_file():
            names.add(name)

    return names


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
