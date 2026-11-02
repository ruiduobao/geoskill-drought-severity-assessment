# Drought Severity Assessment (geoskill-drought-severity-assessment)

> Combined drought grading that fuses SPI (standardized precipitation index, Gamma distribution fitting + normal inversion) with VHI (vegetation health index). Outputs drought grade / SPI rasters plus area statistics JSON.

---

## 1. Overview

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

## 8. License

MIT License. See [`LICENSE`](./LICENSE) for full text.

---

> 中文完整版：[references/SKILL.zh-CN.md](references/SKILL.zh-CN.md)
