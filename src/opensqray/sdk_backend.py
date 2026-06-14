"""Optional Sqray SDK backend.

This module loads a locally installed Sqray SDK runtime at execution time. The
public package does not vendor or redistribute proprietary SDK binaries.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import re
from typing import Any


OPENSQRAY_SDK_DIR_ENV = "OPENSQRAY_SDK_DIR"
OPENSQRAY_SDK_LIB_DIR_ENV = "OPENSQRAY_SDK_LIB_DIR"
OPENSQRAY_SDK_EXTRA_LIB_DIRS_ENV = "OPENSQRAY_SDK_EXTRA_LIB_DIRS"


class SqraySDKUnavailable(RuntimeError):
    """Raised when the optional Sqray SDK backend cannot be loaded."""


class SqraySDKError(RuntimeError):
    """Raised when a loaded Sqray SDK call fails."""


class SqraySDKSlide:
    """Thin ctypes wrapper around the Sqray SDK slide C API."""

    def __init__(
        self,
        path: str | Path,
        *,
        sdk_dir: str | Path | None = None,
        lib_dir: str | Path | None = None,
        _library: Any | None = None,
    ) -> None:
        self._path = Path(path)
        self._library = _library or _load_library(
            sdk_dir=sdk_dir,
            lib_dir=lib_dir,
        )
        _configure_library(self._library)
        self._closed = False
        self._handle = self._open_slide()

    def close(self) -> None:
        """Close the underlying SDK slide handle."""

        if self._closed:
            return
        self._library.sqrayslide_close(self._handle)
        self._closed = True

    def __enter__(self) -> SqraySDKSlide:
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def tile_size(self) -> tuple[int, int]:
        """Return SDK-reported tile size as ``(width, height)``."""

        self._require_open()
        width = ctypes.c_int32()
        height = ctypes.c_int32()
        self._library.sqrayslide_get_tile_size(
            self._handle,
            ctypes.byref(width),
            ctypes.byref(height),
        )
        return width.value, height.value

    @property
    def level_count(self) -> int:
        """Return SDK-reported pyramid level count."""

        self._require_open()
        return int(self._library.sqrayslide_get_level_count(self._handle))

    def level_size(self, level: int) -> tuple[int, int]:
        """Return SDK-reported level size as ``(width, height)``."""

        self._require_open()
        width = ctypes.c_int32()
        height = ctypes.c_int32()
        self._library.sqrayslide_get_level_size(
            self._handle,
            int(level),
            ctypes.byref(width),
            ctypes.byref(height),
        )
        return width.value, height.value

    def level_tile_count(self, level: int) -> tuple[int, int]:
        """Return SDK-reported tile grid as ``(columns, rows)``."""

        self._require_open()
        columns = ctypes.c_int32()
        rows = ctypes.c_int32()
        self._library.sqrayslide_get_level_tile_count(
            self._handle,
            int(level),
            ctypes.byref(columns),
            ctypes.byref(rows),
        )
        return columns.value, rows.value

    def read_tile_jpeg_bytes(self, *, level: int, tile_x: int, tile_y: int) -> bytes:
        """Return raw JPEG bytes for an SDK tile coordinate."""

        self._require_open()
        data_ptr = ctypes.c_void_p()
        size = int(
            self._library.sqrayslide_read_tile_jpeg(
                self._handle,
                ctypes.byref(data_ptr),
                int(tile_x),
                int(tile_y),
                int(level),
            )
        )
        if size < 0 or not data_ptr.value:
            raise SqraySDKError(
                "Sqray SDK failed to read tile JPEG "
                f"at level={level}, tile_x={tile_x}, tile_y={tile_y}"
            )

        try:
            return ctypes.string_at(data_ptr, size)
        finally:
            self._library.sqrayslide_free_memory(data_ptr)

    def read_region_bgra_bytes(
        self,
        *,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> bytes:
        """Return BGRA bytes for an SDK region read."""

        self._require_open()
        x, y = location
        width, height = size
        if width <= 0 or height <= 0:
            raise ValueError("region size must be positive")

        buffer = (ctypes.c_ubyte * (width * height * 4))()
        ok = bool(
            self._library.sqrayslide_read_region_bgra(
                self._handle,
                buffer,
                int(x),
                int(y),
                int(width),
                int(height),
                int(level),
            )
        )
        if not ok:
            raise SqraySDKError(
                "Sqray SDK failed to read region "
                f"at level={level}, location={location}, size={size}"
            )
        return bytes(buffer)

    def _open_slide(self) -> ctypes.c_void_p:
        status = ctypes.c_int()
        handle = self._library.sqrayslide_open(
            os.fsencode(self._path),
            ctypes.byref(status),
        )
        if not handle:
            raise SqraySDKError(
                f"Sqray SDK failed to open slide: {self._path} "
                f"(status={status.value})"
            )
        return handle

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("SqraySDKSlide is closed")


def inspect_sqray_sdk_slide(
    path: str | Path,
    *,
    sdk_dir: str | Path | None = None,
    lib_dir: str | Path | None = None,
) -> dict[str, object]:
    """Inspect SDK-reported slide geometry without exposing SDK internals."""

    with SqraySDKSlide(path, sdk_dir=sdk_dir, lib_dir=lib_dir) as slide:
        level_count = slide.level_count
        return {
            "format": "sdpc",
            "backend": "sqray_sdk",
            "path": str(path),
            "tile_size": _size_dict(slide.tile_size),
            "level_count": level_count,
            "levels": [
                {
                    "level": level,
                    "dimensions": _size_dict(slide.level_size(level)),
                    "tile_grid": _grid_dict(slide.level_tile_count(level)),
                }
                for level in range(level_count)
            ],
        }


def _load_library(
    *,
    sdk_dir: str | Path | None,
    lib_dir: str | Path | None,
) -> ctypes.CDLL:
    resolved_lib_dir = _resolve_lib_dir(sdk_dir=sdk_dir, lib_dir=lib_dir)
    _preload_dependencies(resolved_lib_dir)
    library_path = resolved_lib_dir / _service_library_name()
    if not library_path.exists():
        raise SqraySDKUnavailable(
            f"Sqray SDK service library not found: {library_path}"
        )
    try:
        return ctypes.CDLL(str(library_path))
    except OSError as exc:
        raise SqraySDKUnavailable(
            "Sqray SDK service library could not be loaded. Ensure SDK "
            "dependencies are in the same directory or available through the "
            "platform dynamic-library search path. "
            f"Original loader error: {exc}"
        ) from exc


def _resolve_lib_dir(
    *,
    sdk_dir: str | Path | None,
    lib_dir: str | Path | None,
) -> Path:
    candidates: list[Path] = []
    if lib_dir is not None:
        candidates.append(Path(lib_dir))
    env_lib_dir = os.environ.get(OPENSQRAY_SDK_LIB_DIR_ENV)
    if env_lib_dir:
        candidates.append(Path(env_lib_dir))
    if sdk_dir is not None:
        candidates.append(Path(sdk_dir) / "lib")
    env_sdk_dir = os.environ.get(OPENSQRAY_SDK_DIR_ENV)
    if env_sdk_dir:
        candidates.append(Path(env_sdk_dir) / "lib")

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    raise SqraySDKUnavailable(
        "Sqray SDK library directory is not configured. Set "
        f"{OPENSQRAY_SDK_LIB_DIR_ENV} to the SDK lib directory, or set "
        f"{OPENSQRAY_SDK_DIR_ENV} to an SDK root containing lib/."
    )


def _preload_dependencies(lib_dir: Path) -> None:
    for extra in _extra_lib_dirs():
        if extra.is_dir():
            for library in _dynamic_libraries(extra):
                _try_preload(library)
    for library in _dynamic_libraries(lib_dir):
        if library.name == _service_library_name():
            continue
        _try_preload(library)


def _extra_lib_dirs() -> list[Path]:
    value = os.environ.get(OPENSQRAY_SDK_EXTRA_LIB_DIRS_ENV)
    if not value:
        return []
    return [Path(item) for item in value.split(os.pathsep) if item]


def _dynamic_libraries(lib_dir: Path) -> list[Path]:
    suffixes = _dynamic_library_suffixes()
    return sorted(
        path
        for path in lib_dir.iterdir()
        if path.is_file() and any(path.name.endswith(suffix) for suffix in suffixes)
        and not _is_versioned_macos_dylib_alias(path)
    )


def _is_versioned_macos_dylib_alias(path: Path) -> bool:
    if platform.system() != "Darwin":
        return False
    return bool(re.search(r"\.\d+(?:\.\d+)*\.dylib$", path.name))


def _try_preload(path: Path) -> None:
    try:
        ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
    except (OSError, AttributeError):
        return


def _service_library_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return "libsqrayslideservice.dylib"
    if system == "Windows":
        return "sqrayslideservice.dll"
    return "libsqrayslideservice.so"


def _dynamic_library_suffixes() -> tuple[str, ...]:
    system = platform.system()
    if system == "Darwin":
        return (".dylib",)
    if system == "Windows":
        return (".dll",)
    return (".so",)


def _configure_library(library: Any) -> None:
    library.sqrayslide_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    library.sqrayslide_open.restype = ctypes.c_void_p
    library.sqrayslide_close.argtypes = [ctypes.c_void_p]
    library.sqrayslide_close.restype = None
    library.sqrayslide_free_memory.argtypes = [ctypes.c_void_p]
    library.sqrayslide_free_memory.restype = None
    library.sqrayslide_get_tile_size.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.sqrayslide_get_tile_size.restype = None
    library.sqrayslide_get_level_count.argtypes = [ctypes.c_void_p]
    library.sqrayslide_get_level_count.restype = ctypes.c_int32
    library.sqrayslide_get_level_size.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.sqrayslide_get_level_size.restype = None
    library.sqrayslide_get_level_tile_count.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.sqrayslide_get_level_tile_count.restype = None
    library.sqrayslide_read_tile_jpeg.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    library.sqrayslide_read_tile_jpeg.restype = ctypes.c_int32
    library.sqrayslide_read_region_bgra.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    library.sqrayslide_read_region_bgra.restype = ctypes.c_bool


def _size_dict(size: tuple[int, int]) -> dict[str, int]:
    return {"width": size[0], "height": size[1]}


def _grid_dict(grid: tuple[int, int]) -> dict[str, int]:
    return {"columns": grid[0], "rows": grid[1]}
