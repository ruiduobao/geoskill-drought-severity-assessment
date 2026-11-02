---
name: geoskill-drought-severity-assessment
description: '融合 SPI（标准化降水指数，Gamma 分布拟合+正态反演）与 VHI（植被健康指数）的综合干旱分级。Combined drought grading fusing SPI (Gamma-fit standardized precipitation index) and VHI (vegetation health index). 输出干旱等级/SPI 栅格 + 面积统计 JSON。'
---

# 干旱严重度评估 | Drought Severity Assessment

A combined drought assessment fusing meteorological (precipitation) and remote-sensing vegetation information, suitable for regional drought monitoring, agricultural drought early warning, and time-series drought comparison. It implements two complementary indices:

- **SPI** (Standardized Precipitation Index): fits a Gamma distribution to the precipitation series (including the mixed zero-precipitation probability p0), then applies the standard-normal inverse (via `norm.ppf`) to the cumulative probability. SPI < 0 indicates drier-than-normal conditions; the larger the absolute value, the drier. Its distribution approximates the standard normal.
- **VHI** (Vegetation Health Index): based on the standardized NDVI anomaly (current NDVI relative to the multi-year mean / standard deviation). A negative anomaly indicates vegetation stress (agricultural drought).

SPI and VHI are combined with equal weights into a composite drought index (both are approximately standard-normal), then classified by thresholds into five grades: no drought / mild / moderate / severe / extreme. Outputs a drought-grade raster, an SPI raster, and per-grade area statistics.

`--synthetic` mode generates multi-epoch precipitation + NDVI data (precipitation plunges and NDVI drops in the right-side region at the final epoch, simulating a regional meteorological–agricultural drought), letting you validate the workflow without network access or real data.

## Dependencies / 依赖

```bash
pip install numpy rasterio scipy
```

## Usage / 使用方法

### Basic usage (synthetic data, offline)

```bash
python geoskill-drought-severity-assessment.py --bbox 116.0 39.0 117.0 40.0 --n-dates 12 --output-dir ./output
```

### Example 1: drought assessment on synthetic data

```bash
python geoskill-drought-severity-assessment.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --n-dates 12 \
    --synthetic \
    --output-dir ./drought_syn
```

### Example 2: more time steps

```bash
python geoskill-drought-severity-assessment.py \
    --bbox 116.0 39.0 117.0 40.0 \
    --n-dates 24 \
    --synthetic \
    --output-dir ./drought_24
```

### Example 3: real precipitation time series

```bash
python geoskill-drought-severity-assessment.py \
    --input precip_monthly.tif \
    --output-dir ./real_drought
```

(The input is a multi-band GeoTIFF, one band per precipitation epoch; this mode grades with SPI only.)

### Example 4: different region

```bash
python geoskill-drought-severity-assessment.py --bbox 121 31 122 32 --n-dates 12 --synthetic --output-dir ./shanghai --quiet
```

## Output / 输出

| File | Format | Description |
|---|---|---|
| `drought_grade.tif` | GeoTIFF (uint8) | Drought grade 0=none 1=mild 2=moderate 3=severe 4=extreme, EPSG:4326 |
| `spi.tif` | GeoTIFF (float32) | Standardized Precipitation Index (SPI) |
| `drought_report.json` | JSON | SPI Gamma parameters, pixel count/area per grade, drought ratio |
| `output-manifest.json` | JSON | Run manifest (input/output/QA/software versions) |

## Data Source / 数据源 / Source

- **Precipitation**: local multi-band GeoTIFF, or from CHIRPS / GPM IMERG / station interpolation
- **NDVI**: generated in synthetic mode; real applications may use MODIS / Landsat time series
- **Synthetic mode**: generated locally, no external data source

## Privacy / 隐私声明 / Privacy

- Runs fully offline by default and makes no network requests
- `--synthetic` mode reads no external data
- All computation is done locally; no user data is uploaded

## License / License

MIT

---

> 中文完整版：需要时再读 [references/SKILL.zh-CN.md](references/SKILL.zh-CN.md)，不要默认全量加载。
