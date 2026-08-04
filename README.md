# Drought Severity Assessment (geoskill-drought-severity-assessment)

> Combined drought grading that fuses SPI (standardized precipitation index, Gamma distribution fitting + normal inversion) with VHI (vegetation health index). Outputs drought grade / SPI rasters plus area statistics JSON.

---

## 1. Overview

A combined drought assessment fusing meteorological (precipitation) and remote-sensing vegetation information, suitable for regional drought monitoring, agricultural drought early warning, and time-series drought comparison. Two complementary indices are implemented: - **SPI** (Standardized Precipitation Index): fit a Gamma distribution to the precipitation series (including the mixed probability p0 of zero precipitation), then apply the standard normal inversion (`norm.ppf`) to the cumulative probability. SPI < 0 indicates drier than normal, and the larger the absolute value, the drier; its distribution is approximately standard normal. - **VHI** (Vegetation Health Index): based on the standardized NDVI anomaly (current NDVI relative to the multi-year mean/standard deviation). A negative anomaly indicates vegetation stress (agricultural drought). SPI and VHI are combined with equal weights into a composite drought index (both are approximately standard normal), classified by thresholds into five grades: none / mild / moderate / severe / extreme drought. Outputs a drought grade raster, an SPI raster, and per-grade area statistics. The `--synthetic` mode generates multi-epoch precipitation + NDVI data (the right-side region shows a sharp late-period precipitation drop and NDVI decline, simulating a regional meteorological-agricultural drought), allowing the workflow to be validated without network access or real data.

## 2. Features

A combined drought assessment fusing meteorological (precipitation) and remote-sensing vegetation information, suitable for regional drought monitoring, agricultural drought early warning, and time-series drought comparison. Two complementary indices are implemented: - **SPI** (Standardized Precipitation Index): fit a Gamma distribution to the precipitation series (including the mixed probability p0 of zero precipitation), then apply the standard normal inversion (`norm.ppf`) to the cumulative probability. SPI < 0 indicates drier than normal, and the larger the absolute value, the drier; its distribution is approximately standard normal. - **VHI** (Vegetation Health Index): based on the standardized NDVI anomaly (current NDVI relative to the multi-year mean/standard deviation). A negative anomaly indicates vegetation stress (agricultural drought). SPI and VHI are combined with equal weights into a composite drought index (both are approximately standard normal), classified by thresholds into five grades: none / mild / moderate / severe / extreme drought. Outputs a drought grade raster, an SPI raster, and per-grade area statistics. The `--synthetic` mode generates multi-epoch precipitation + NDVI data (the right-side region shows a sharp late-period precipitation drop and NDVI decline, simulating a regional meteorological-agricultural drought), allowing the workflow to be validated without network access or real data.

## 3. Quick Start

```bash
pip install -r requirements.txt
python geoskill-drought-severity-assessment.py --bbox 116 39 117 40 --synthetic --output-dir ./out
```

## 4. CLI Parameters

Run `python <skill>.py --help` for the full list. Common parameters:

| Parameter | Type | Description |
|---|---|---|
| `--bbox` | `float[4]` | WGS84 bounding box `min_lon min_lat max_lon max_lat` |
| `--input` | `path` | Local input file (GeoJSON/GeoTIFF/etc.) |
| `--output-dir` | `path` | Output directory (default `./output`) |
| `--synthetic` | `flag` | Use synthetic data instead of real input |
| `--quiet` | `flag` | Suppress non-essential stdout |

## 5. Input / Output

| File | Format | Description |
|---|---|---|
| `drought_grade.tif` | GeoTIFF (uint8) | Drought grade 0=none 1=mild 2=moderate 3=severe 4=extreme, EPSG:4326 |
| `spi.tif` | GeoTIFF (float32) | Standardized Precipitation Index (SPI) |
| `drought_report.json` | JSON | SPI Gamma parameters, per-grade pixel counts/areas, drought ratio |
| `output-manifest.json` | JSON | Run manifest (inputs/outputs/QA/software versions) |

## 6. Technical Principle

(see SKILL.md for details)

## 7. Methodology

This skill has been methodologically reviewed. See [`REVIEW.md`](./REVIEW.md) for:

- P0/P1/P2 issue counts and verdicts
- Reproduction commands
- Known limitations and edge cases

## 8. License

MIT License. See [`LICENSE`](./LICENSE) for full text.

---

# 干旱严重度评估（中文版）

> 本部分为完整中文文档，与上方英文部分对应。

---
name: geoskill-drought-severity-assessment
description: '融合 SPI（标准化降水指数，Gamma 分布拟合+正态反演）与 VHI（植被健康指数）的综合干旱分级。Combined drought grading fusing SPI (Gamma-fit standardized precipitation index) and VHI (vegetation health index). 输出干旱等级/SPI 栅格 + 面积统计 JSON。'
---

# 干旱严重度评估 | Drought Severity Assessment

融合气象（降水）与遥感植被信息的综合干旱评估，适用于区域旱情监测、农业干旱
预警、时序旱情对比等场景。实现两个互补指数：

- **SPI**（Standardized Precipitation Index，标准化降水指数）：对降水序列拟合
  Gamma 分布（含零降水混合概率 p0），经累积概率后用标准正态反演
  （`norm.ppf`）。SPI < 0 表示偏干，绝对值越大越干；其分布近似标准正态。
- **VHI**（Vegetation Health Index，植被健康指数）：基于 NDVI 标准化距平
  （当期 NDVI 相对多年均值/标准差）。负距平表示植被受胁迫（农业干旱）。

将 SPI 与 VHI 等权合成为综合干旱指数（两者均近似标准正态），按阈值分为五级：
无旱 / 轻旱 / 中旱 / 重旱 / 特旱。输出干旱等级栅格、SPI 栅格与逐等级面积统计。

支持 `--synthetic` 模式生成多期降水 + NDVI 数据（右侧区域末期降水骤降、NDVI
下降，模拟一场区域性气象—农业干旱），无需网络和真实数据即可验证流程。

## 依赖

```bash
pip install numpy rasterio scipy
```

## 使用方法

### 基本用法（合成数据，离线）

```bash
python geoskill-drought-severity-assessment.py --bbox 116.0 39.0 117.0 40.0 --n-dates 12 --output-dir ./output
```

### 示例 1：合成数据干旱评估

```bash
python geoskill-drought-severity-assessment.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --n-dates 12 \
    --synthetic \
    --output-dir ./drought_syn
```

### 示例 2：更多时间步

```bash
python geoskill-drought-severity-assessment.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --n-dates 24 \
    --synthetic \
    --output-dir ./drought_24
```

### 示例 3：真实降水时间序列

```bash
python geoskill-drought-severity-assessment.py \
    --input precip_monthly.tif \
    --output-dir ./real_drought
```

（输入为多波段 GeoTIFF，每个波段 = 一期降水；此模式仅用 SPI 分级。）

### 示例 4：不同区域

```bash
python geoskill-drought-severity-assessment.py --bbox 121 31 122 32 --n-dates 12 --synthetic --output-dir ./shanghai --quiet
```

## 输出

| 文件 | 格式 | 说明 |
|---|---|---|
| `drought_grade.tif` | GeoTIFF (uint8) | 干旱等级 0=无旱 1=轻旱 2=中旱 3=重旱 4=特旱，EPSG:4326 |
| `spi.tif` | GeoTIFF (float32) | 标准化降水指数 SPI |
| `drought_report.json` | JSON | SPI Gamma 参数、各级像元数/面积、干旱比例 |
| `output-manifest.json` | JSON | 运行清单（输入/输出/QA/软件版本） |

## 数据源 / Source

- **降水**：本地多波段 GeoTIFF，或来自 CHIRPS / GPM IMERG / 地面站点插值
- **NDVI**：合成模式生成，真实应用可来自 MODIS / Landsat 时序
- **合成模式**：本地生成，无外部数据源

## 隐私声明 / Privacy

- 默认完全离线运行，不发起任何网络请求
- `--synthetic` 模式不读取任何外部数据
- 所有计算在本地完成，不上传用户数据

## License

MIT
