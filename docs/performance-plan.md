# High-Throughput Patch Extraction Plan

OpenSqray must support practical preprocessing workloads over thousands of
SDPC slides. The first implementation favors correctness and bounded resource
use over aggressive shared-handle concurrency.

## Current API

`opensqray.batch` provides:

- `RegionRequest(location, level, size, key=None)`
- `iter_patch_requests(dimensions, patch_size, stride=..., level=...)`
- `read_regions(path, requests, workers=..., sdk_dir=..., sdk_lib_dir=...)`
- `iter_regions(path, requests, workers=..., chunk_size=..., sdk_dir=..., sdk_lib_dir=...)`
- `recommended_worker_count(slide_count=..., max_workers=...)`

`OpenSqraySlide` also exposes:

- `slide.read_regions(requests, workers=...)`
- `slide.iter_regions(requests, workers=..., chunk_size=...)`

Single-region behavior stays OpenSlide-like:

```python
from opensqray import OpenSqraySlide

with OpenSqraySlide("slide.sdpc") as slide:
    region = slide.read_region((0, 0), 0, (512, 512))
```

Batch region reads:

```python
from opensqray import OpenSqraySlide, RegionRequest

requests = [
    RegionRequest((0, 0), 0, (512, 512)),
    RegionRequest((512, 0), 0, (512, 512)),
]

with OpenSqraySlide("slide.sdpc") as slide:
    images = slide.read_regions(requests, workers=4)
```

Grid patch generation:

```python
from opensqray import OpenSqraySlide, iter_patch_requests

with OpenSqraySlide("slide.sdpc") as slide:
    requests = iter_patch_requests(
        slide.dimensions,
        patch_size=(512, 512),
        stride=(512, 512),
        level=0,
    )
    for image in slide.read_regions(requests, workers=4):
        ...
```

For large jobs, prefer streaming results by chunk:

```python
from opensqray import OpenSqraySlide, iter_patch_requests

with OpenSqraySlide("slide.sdpc") as slide:
    requests = iter_patch_requests(slide.dimensions, 512, stride=512)
    for result in slide.iter_regions(requests, workers=4, chunk_size=64):
        patch_id = result.key
        image = result.image
        ...
```

## Concurrency Model

Parallel reads use one slide handle per worker. OpenSqray does not share one SDK
handle across threads because the vendor SDK thread-safety contract is not yet
documented. This model has predictable behavior:

- No cross-thread mutation of one SDK handle.
- Each worker amortizes `open()` cost across a chunk of requests.
- Result order matches request order.
- Worker count is explicit and bounded.

For many-slide jobs, prefer process-level orchestration outside one Python
object:

```python
from concurrent.futures import ProcessPoolExecutor
from opensqray import RegionRequest, read_regions

def process_slide(path: str) -> int:
    requests = [RegionRequest((0, 0), 0, (512, 512))]
    images = read_regions(path, requests, workers=2)
    return len(images)

with ProcessPoolExecutor(max_workers=8) as executor:
    counts = list(executor.map(process_slide, slide_paths))
```

## Practical Defaults

Recommended starting points:

| Workload | Suggested parallelism |
| --- | --- |
| One slide, a few patches | `workers=1` |
| One slide, many patches | `workers=2..8`, benchmark locally |
| Many slides | outer process pool over slides, inner `workers=1..2` |
| Network storage | fewer workers; avoid saturating metadata and I/O |
| Local NVMe | more workers can help until CPU decode or I/O saturates |

Avoid multiplying outer and inner worker counts blindly. For example, 16
processes each using 8 inner workers opens 128 SDK handles and can overload the
filesystem or SDK runtime.

## Patch Coordinate Semantics

`RegionRequest.location` follows OpenSlide: it is always in level-0 pixel
coordinates. `RegionRequest.size` is the output size at the requested level.

`iter_patch_requests()` generates a simple level-0 coordinate grid. For
downsampled levels, pass a level-0 stride that matches the desired sampling
density.

## Memory Rules

Region reads materialize Pillow images. A 512 x 512 RGBA patch is about 1 MB
before compression. Large batch calls can therefore consume substantial memory.

Guidelines:

- Stream requests in chunks instead of building millions at once.
- Write or consume patches immediately.
- Prefer raw tile JPEG reads when the downstream pipeline can consume JPEG
  bytes without decoding.
- Keep worker count bounded.

## Benchmark Plan

Before claiming production throughput, run a local benchmark matrix on real
SDPC data:

- platforms: Linux x86_64, Linux arm64, Windows x86_64, macOS Apple Silicon,
  macOS Intel when a vendor runtime is available
- storage: local SSD/NVMe and target production storage
- patch sizes: 256, 512, 1024
- levels: 0 and at least one downsampled level
- workers: 1, 2, 4, 8, 16
- outputs: patches/sec, median latency, p95 latency, memory, open handles,
  error rate

The benchmark should distinguish:

- SDK `read_region_bgra` cost
- BGRA-to-Pillow conversion cost
- JPEG encode/save cost when writing files
- external model preprocessing cost

OpenSqray includes a bounded benchmark helper:

```bash
python3 tools/benchmark_patch_reads.py data/20220514_145829_0.sdpc \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --patch-size 256 \
  --count 128 \
  --workers 4 \
  --chunk-size 32
```

## Future Work

- Add optional NumPy output to reduce Pillow overhead in ML pipelines.
- Add tile JPEG batch helpers for pipelines that can consume JPEG bytes.
- Revisit shared-handle threading only if the SDK vendor documents it as safe.
