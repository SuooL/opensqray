# OpenSqray

[![CI](https://github.com/SuooL/opensqray/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SuooL/opensqray/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)

**语言 / Language**: 简体中文 | [English](README.en.md)

**教程**: [Jupyter Tutorial](examples/opensqray_tutorial.ipynb)

OpenSqray 是一个面向全切片病理图像（Whole Slide Image, WSI）的 Python 工具库，当前重点支持 Sqray SDPC 文件的公开安全解析、元数据检查、候选 JPEG 资源提取，以及可选的 SDK 后端读图能力。对 SVS 等通用 WSI 格式，OpenSqray 通过可选 OpenSlide 依赖进行检查，不重复造一套私有解析器。

项目目标不是把未公开格式“猜成确定协议”，而是提供一个可测试、可复现、边界清楚的工程层：能原生解析的内容原生解析；需要官方运行时才能可靠完成的像素读取，明确交给可选 SDK 后端。

## 功能概览

- SDPC 基础元数据解析：尺寸、层级数、tile size、缩略图尺寸、扫描倍率、设备/扫描相关字符串等。
- 嵌入 JPEG 记录扫描：过滤明显 false positive，只返回可解析的 JPEG 记录。
- Associated image 候选：可列出和导出 label/macro 等候选 JPEG 资源。
- Tile index 研究工具：提供 row-major 候选 tile 映射和 index-table 诊断输出。
- OpenSlide-like `SDPCSlide` facade：提供 `dimensions`、`level_dimensions`、`properties`、tile JPEG byte 读取等接口。
- 可选 Pillow 解码：安装 `opensqray[image]` 后可将候选 JPEG 或 SDK BGRA region 转成图像对象。
- 可选 Sqray SDK 后端：在用户本地具备合法 SDK runtime 时，提供更可靠的 SDPC tile JPEG 与 region 读取。
- 可选 OpenSlide 后端：用于 SVS 等 OpenSlide 支持的标准格式检查。

## 效果预览

![OpenSqray API demo](docs/assets/opensqray-api-demo.svg)

上图是公开安全的合成流程示意图，展示 OpenSqray 的典型调用路径：原生解析用于元数据与候选资源研究，SDK 后端用于坐标准确的 tile/region 读取。

下面是真实公开 SDPC 样本 `20220514_145829_0.sdpc` 的 associated-image 导出效果，由 `opensqray extract-associated` 直接生成。候选名称仍是启发式命名，不代表已确认的官方 SDPC directory entry。

| `label_candidate` | `macro_candidate` |
| --- | --- |
| <img src="docs/assets/20220514_145829_0-0000-label_candidate.jpg" alt="Real SDPC label candidate" width="280"> | <img src="docs/assets/20220514_145829_0-0001-macro_candidate.jpg" alt="Real SDPC macro candidate" width="520"> |

想看可复现的真实文件执行过程，可以打开 [examples/opensqray_tutorial.ipynb](examples/opensqray_tutorial.ipynb)。该 notebook 默认读取本地 `data/20220514_145829_0.sdpc`，也可以通过 `OPENSQRAY_TUTORIAL_SDPC=/path/to/file.sdpc` 指向其他 SDPC 文件，并实际运行 OpenSqray parser、`SDPCSlide` 和 CLI。公开仓库不分发 `data/` 中的真实切片文件；如果你从 GitHub 克隆项目，需要在本地提供自己的 SDPC 文件后再运行 notebook。

## 安装

从源码安装：

```bash
git clone https://github.com/SuooL/opensqray.git
cd opensqray
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

安装图像解码能力：

```bash
python -m pip install -e ".[image]"
```

安装 OpenSlide Python 绑定：

```bash
python -m pip install -e ".[openslide]"
```

使用 SVS 等 OpenSlide-backed 格式时，还需要系统中已安装 OpenSlide native library。

配置可选 Sqray SDK 后端：

```bash
export OPENSQRAY_SDK_LIB_DIR=/path/to/sqrayslide/lib
# 或者：
export OPENSQRAY_SDK_DIR=/path/to/sqrayslide
```

如果 SDK runtime 还依赖额外 native library 目录：

```bash
export OPENSQRAY_SDK_EXTRA_LIB_DIRS=/path/to/extra/libs
```

OpenSqray 不随仓库分发、复制或再打包任何专有 SDK 二进制文件。

## 快速开始

检查 SDPC 元数据：

```bash
opensqray inspect path/to/slide.sdpc --compact
```

列出 associated image 候选：

```bash
opensqray associated path/to/slide.sdpc --compact
```

导出 associated image 候选 JPEG：

```bash
opensqray extract-associated path/to/slide.sdpc \
  --output-dir associated-images
```

查看 tile-grid 候选：

```bash
opensqray tile-index path/to/slide.sdpc \
  --preview-limit 30 \
  --compact
```

读取一个候选 tile JPEG：

```bash
opensqray read-tile path/to/slide.sdpc \
  --backend native \
  --preview-limit 100 \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-native.jpg
```

使用 SDK 后端读取 tile：

```bash
opensqray read-tile path/to/slide.sdpc \
  --backend sdk \
  --sdk-lib-dir /path/to/sqrayslide/lib \
  --level 0 --tile-x 0 --tile-y 0 \
  --output tile-sdk.jpg
```

检查 SVS 等 OpenSlide 支持的文件：

```bash
opensqray inspect path/to/slide.svs --compact
```

如果 OpenSlide 不可用，CLI 会返回清晰的依赖提示，而不是尝试用 SDPC parser 解析 SVS。

## Python API

原生 SDPC 元数据与候选 JPEG：

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    print(slide.dimensions)
    print(slide.level_dimensions)
    print(slide.level_downsamples)
    print(slide.properties["opensqray.backend"])

    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
```

解码候选 JPEG 需要安装 `opensqray[image]`：

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc") as slide:
    tile_image = slide.read_tile_image(level=0, tile_x=0, tile_y=0)
```

SDK 后端 region 读取：

```python
from opensqray import SDPCSlide

with SDPCSlide("path/to/slide.sdpc", backend="sdk") as slide:
    tile_jpeg = slide.read_tile_jpeg_bytes(level=0, tile_x=0, tile_y=0)
    region_bgra = slide.read_region_bgra_bytes((0, 0), 0, (512, 512))
    region_image = slide.read_region((0, 0), 0, (512, 512))
```

`read_region()` 会把 SDK 返回的 BGRA bytes 转成 Pillow RGBA image，因此需要安装 `opensqray[image]`。

## 后端能力边界

OpenSqray 当前有两个 SDPC 路径：

- `backend="native"`：公开 parser 路径，不依赖专有 runtime，适合元数据、associated image 候选、tile/index 研究和 preview-limited tile JPEG byte 读取。
- `backend="sdk"`：可选官方 runtime adapter，适合需要坐标准确 tile JPEG 或 region read 的场景。

| 能力 | Native 后端 | SDK 后端 |
| --- | --- | --- |
| SDPC 元数据 / properties | 支持 | 支持，并可通过 `sdk-info` 获取 SDK 几何信息 |
| level dimensions / downsamples | 基于已解析信息推断 | SDK 几何信息可用 |
| associated images | 启发式 JPEG 候选 | 尚未封装 |
| 按坐标读取 tile JPEG | 启发式、受 preview 限制 | 支持 |
| `read_region_bgra_bytes()` | 尚未实现 | 支持 |
| `read_region()` | 抛出 `NotImplementedError` | 安装 Pillow 后支持 |
| color correction / ICC | 尚未实现 | 尚未封装 |
| fluorescence / channels / focal planes | 尚未实现 | 尚未封装 |
| 完整 OpenSlide API 兼容 | 尚未达到 | 只覆盖 tile/region 相关子集 |

即使启用 SDK 后端，OpenSqray 目前也还不是 `openslide.OpenSlide` 的完整 drop-in replacement。当前 facade 覆盖了最常用的 metadata、tile JPEG 和 region read；`get_thumbnail()`、标准 OpenSlide associated image mapping、OpenSlide error-latching、DeepZoom helper、ICC/color correction 以及更多 SDK 专有能力仍在路线图中。

## 输出契约

SDPC inspection 输出版本化 JSON，当前 schema 为：

```text
opensqray.sdpc.metadata.v1
```

稳定字段与研究诊断字段会分开输出，避免下游把 reverse-engineering 证据误当作已确认格式协议。`index-research` 也使用独立 schema：

```text
opensqray.sdpc.index_research.v4
```

这些诊断结果用于格式研究，不应直接视为完整 SDPC tile directory。

## 路线图

- [x] 项目骨架、CLI、synthetic fixture 测试。
- [x] SDPC metadata parser 与版本化 JSON 输出。
- [x] associated image 候选发现与导出。
- [x] tile-grid 候选与 index-research 诊断。
- [x] `SDPCSlide` facade、Pillow 解码适配、SDK backend MVP。
- [ ] 更完整的 SDPC tile directory 映射与跨样本验证。
- [ ] OpenSlide-compatible compatibility layer。
- [ ] thumbnail、associated image 标准映射、ICC/color correction。
- [ ] 私有部署场景下的 SDK runtime 打包策略文档。

## 开发

运行测试：

```bash
python3 -m unittest discover -s tests
```

测试使用 synthetic fixtures，不依赖真实切片数据或专有 SDK。

## 安全与数据边界

OpenSqray 仓库保存公开源码、测试 fixture、文档，以及从公开 SDPC 样本导出的轻量预览图；不包含完整真实切片样本、可识别患者数据、专有 SDK 二进制文件或非公开实现。需要 SDK 后端时，请在自己的运行环境中配置合法 SDK runtime。

## 致谢

OpenSqray 的 SDPC 研究与工程设计参考了 [OpenSDPC](https://github.com/WonderLandxD/opensdpc) 的公开工作。OpenSqray 不复制或再分发其代码；相关格式理解会保持来源边界和实现边界清晰。

## 许可证

当前尚未选择开源许可证。仓库公开可见不代表授予使用、复制、分发或修改权利；正式复用前请等待仓库所有者补充许可证。
