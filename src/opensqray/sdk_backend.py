"""Optional Sqray SDK backend.

This module loads a locally installed Sqray SDK runtime at execution time. The
public package does not vendor or redistribute proprietary SDK binaries.
"""

from __future__ import annotations

import ctypes
import importlib.resources
import importlib.util
import os
from pathlib import Path
import platform
import re
from typing import Any


OPENSQRAY_SDK_DIR_ENV = "OPENSQRAY_SDK_DIR"
OPENSQRAY_SDK_LIB_DIR_ENV = "OPENSQRAY_SDK_LIB_DIR"
OPENSQRAY_SDK_EXTRA_LIB_DIRS_ENV = "OPENSQRAY_SDK_EXTRA_LIB_DIRS"
OPENSQRAY_SDK_RUNTIME_PACKAGE_ENV = "OPENSQRAY_SDK_RUNTIME_PACKAGE"
DEFAULT_SDK_RUNTIME_PACKAGE = "opensqray_sdk_runtime"

SDK_ASSOCIATED_IMAGE_TYPES = {
    "label": 0,
    "thumbnail": 1,
    "macro": 2,
}

_WINDOWS_DLL_DIRECTORY_HANDLES: list[Any] = []
_LINUX_SDK_PRELOAD_LIBRARY_NAMES = (
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

    def level_downsample(self, level: int) -> float:
        """Return SDK-reported level downsample."""

        self._require_open()
        return float(
            self._library.sqrayslide_get_level_downsample(
                self._handle,
                int(level),
            )
        )

    def best_level_for_downsample(self, downsample: float) -> int:
        """Return SDK-reported best level for a requested downsample."""

        self._require_open()
        return int(
            self._library.sqrayslide_get_best_level_for_downsample(
                self._handle,
                float(downsample),
            )
        )

    @property
    def mpp(self) -> tuple[float, float]:
        """Return SDK-reported microns-per-pixel as ``(mpp_x, mpp_y)``."""

        self._require_open()
        x = ctypes.c_double()
        y = ctypes.c_double()
        self._library.sqrayslide_get_mpp(
            self._handle,
            ctypes.byref(x),
            ctypes.byref(y),
        )
        return float(x.value), float(y.value)

    @property
    def magnification(self) -> float:
        """Return SDK-reported scan magnification."""

        self._require_open()
        magnification = ctypes.c_float()
        self._library.sqrayslide_get_magnification(
            self._handle,
            ctypes.byref(magnification),
        )
        return float(magnification.value)

    @property
    def barcode(self) -> str | None:
        """Return SDK-reported barcode when available."""

        self._require_open()
        value = self._library.sqrayslide_get_barcode(self._handle)
        if not value:
            return None
        return os.fsdecode(value)

    def read_associated_jpeg_bytes(self, name: str) -> tuple[tuple[int, int], bytes]:
        """Return SDK label/thumbnail/macro JPEG bytes by associated-image name."""

        self._require_open()
        try:
            image_type = SDK_ASSOCIATED_IMAGE_TYPES[name]
        except KeyError as exc:
            allowed = ", ".join(sorted(SDK_ASSOCIATED_IMAGE_TYPES))
            raise KeyError(
                f"unknown SDK associated image: {name}; expected {allowed}"
            ) from exc

        width = ctypes.c_int32()
        height = ctypes.c_int32()
        data_ptr = ctypes.c_void_p()
        data_size = ctypes.c_int32()
        ok = bool(
            self._library.sqrayslide_read_label_jpeg(
                self._handle,
                int(image_type),
                ctypes.byref(width),
                ctypes.byref(height),
                ctypes.byref(data_ptr),
                ctypes.byref(data_size),
            )
        )
        if not ok or not data_ptr.value or data_size.value <= 0:
            raise SqraySDKError(f"Sqray SDK failed to read associated image: {name}")

        try:
            return (width.value, height.value), ctypes.string_at(
                data_ptr,
                data_size.value,
            )
        finally:
            self._library.sqrayslide_free_memory(data_ptr)

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
        return _force_opaque_bgra_bytes(bytes(buffer))

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
            "mpp": {"x": slide.mpp[0], "y": slide.mpp[1]},
            "magnification": slide.magnification,
            "barcode": slide.barcode,
            "levels": [
                {
                    "level": level,
                    "dimensions": _size_dict(slide.level_size(level)),
                    "downsample": slide.level_downsample(level),
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
            "On macOS, the current Sqray SDK package may require setting "
            "DYLD_LIBRARY_PATH to include the SDK lib directory and the OpenMP "
            "runtime directory before starting Python. "
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
    if sdk_dir is not None:
        candidates.extend(_sdk_root_library_dirs(Path(sdk_dir)))
    candidates.extend(_packaged_runtime_lib_dirs())

    env_lib_dir = os.environ.get(OPENSQRAY_SDK_LIB_DIR_ENV)
    if env_lib_dir:
        candidates.append(Path(env_lib_dir))
    env_sdk_dir = os.environ.get(OPENSQRAY_SDK_DIR_ENV)
    if env_sdk_dir:
        candidates.extend(_sdk_root_library_dirs(Path(env_sdk_dir)))

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    raise SqraySDKUnavailable(
        "Sqray SDK library directory is not configured. Set "
        f"{OPENSQRAY_SDK_LIB_DIR_ENV} to the SDK lib directory, or set "
        f"{OPENSQRAY_SDK_DIR_ENV} to an SDK root containing lib/."
    )


def _preload_dependencies(lib_dir: Path) -> None:
    _register_windows_dll_directory(lib_dir)
    if platform.system() == "Linux":
        for extra in _extra_lib_dirs():
            if extra.is_dir():
                for library in _linux_preload_libraries(extra):
                    _try_preload(library)
        for library in _linux_preload_libraries(lib_dir):
            _try_preload(library)
        return

    for extra in _extra_lib_dirs():
        if extra.is_dir():
            _register_windows_dll_directory(extra)
            for library in _dynamic_libraries(extra):
                _try_preload(library)
    for library in _dynamic_libraries(lib_dir):
        if library.name == _service_library_name():
            continue
        _try_preload(library)


def _linux_preload_libraries(lib_dir: Path) -> list[Path]:
    """Return Linux SDK dependencies without loading duplicate soname copies."""

    return [
        lib_dir / name
        for name in _LINUX_SDK_PRELOAD_LIBRARY_NAMES
        if (lib_dir / name).is_file()
    ]


def _extra_lib_dirs() -> list[Path]:
    value = os.environ.get(OPENSQRAY_SDK_EXTRA_LIB_DIRS_ENV)
    if not value:
        return []
    return [Path(item) for item in value.split(os.pathsep) if item]


def _dynamic_libraries(lib_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in lib_dir.iterdir()
        if path.is_file() and _is_dynamic_library(path)
        and not _is_versioned_macos_dylib_alias(path)
    )


def _is_dynamic_library(path: Path) -> bool:
    system = platform.system()
    if system == "Darwin":
        return path.name.endswith(".dylib")
    if system == "Windows":
        return path.name.lower().endswith(".dll")
    return path.name.endswith(".so") or ".so." in path.name


def _is_versioned_macos_dylib_alias(path: Path) -> bool:
    if platform.system() != "Darwin":
        return False
    return bool(re.search(r"\.\d+(?:\.\d+)*\.dylib$", path.name))


def _register_windows_dll_directory(path: Path) -> None:
    if platform.system() != "Windows" or not hasattr(os, "add_dll_directory"):
        return
    try:
        handle = os.add_dll_directory(str(path))
    except OSError:
        return
    _WINDOWS_DLL_DIRECTORY_HANDLES.append(handle)


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


def _sdk_root_library_dirs(sdk_root: Path) -> list[Path]:
    if platform.system() == "Windows":
        return [sdk_root / "bin", sdk_root / "lib"]
    return [sdk_root / "lib"]


def _packaged_runtime_lib_dirs() -> list[Path]:
    candidates: list[Path] = []
    for package_name in _runtime_package_names():
        if importlib.util.find_spec(package_name) is None:
            continue
        try:
            package_root = importlib.resources.files(package_name)
        except (ModuleNotFoundError, ValueError):
            continue
        root = Path(str(package_root))
        platform_tag = _platform_runtime_tag()
        if platform.system() == "Windows":
            candidates.append(root / platform_tag / "bin")
        candidates.append(root / platform_tag / "lib")
        if platform.system() == "Windows":
            candidates.append(root / "bin")
        candidates.append(root / "lib")
    return candidates


def _runtime_package_names() -> tuple[str, ...]:
    value = os.environ.get(OPENSQRAY_SDK_RUNTIME_PACKAGE_ENV)
    if value:
        return tuple(item for item in value.split(os.pathsep) if item)
    return (DEFAULT_SDK_RUNTIME_PACKAGE,)


def _platform_runtime_tag() -> str:
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
    library.sqrayslide_get_level_downsample.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
    ]
    library.sqrayslide_get_level_downsample.restype = ctypes.c_double
    library.sqrayslide_get_best_level_for_downsample.argtypes = [
        ctypes.c_void_p,
        ctypes.c_double,
    ]
    library.sqrayslide_get_best_level_for_downsample.restype = ctypes.c_int32
    library.sqrayslide_get_mpp.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    library.sqrayslide_get_mpp.restype = None
    library.sqrayslide_get_magnification.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
    ]
    library.sqrayslide_get_magnification.restype = None
    library.sqrayslide_get_barcode.argtypes = [ctypes.c_void_p]
    library.sqrayslide_get_barcode.restype = ctypes.c_char_p
    library.sqrayslide_read_label_jpeg.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.sqrayslide_read_label_jpeg.restype = ctypes.c_bool
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


def _force_opaque_bgra_bytes(data: bytes) -> bytes:
    """Normalize SDK alpha bytes for deterministic OpenSlide-like output."""

    normalized = bytearray(data)
    normalized[3::4] = b"\xff" * (len(normalized) // 4)
    return bytes(normalized)
