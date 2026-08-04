#!/usr/bin/env python3
"""drought-severity-assessment — 干旱严重度评估

融合气象与遥感植被信息的综合干旱评估。实现两个核心指数：

- **SPI**（Standardized Precipitation Index，标准化降水指数）：对降水序列拟合
  Gamma 分布（含零降水混合概率），经累积概率后用标准正态反演（norm.ppf）。
  SPI < 0 表示偏干，绝对值越大越干。
- **VHI**（Vegetation Health Index，植被健康指数）：基于 NDVI 距平（当期 NDVI
  相对多年均值的标准化偏差），负距平表示植被受胁迫。

将 SPI 与 VHI 合成一个综合干旱指数（两者均近似标准正态，等权平均），按阈值
分级：无旱 / 轻旱 / 中旱 / 重旱 / 特旱。输出干旱等级栅格、SPI 栅格与面积统计 JSON。

数据源：本地多波段 GeoTIFF（逐波段 = 逐期降水），或 ``--synthetic`` 生成多期
降水 + NDVI（部分区域降水偏低）的模拟数据集用于离线测试。

隐私声明 / Privacy：
- 默认完全离线运行，不发起任何网络请求。
- ``--synthetic`` 模式完全无网络。
- 所有处理在本地完成，不上传任何用户数据。

Usage:
    python drought-severity-assessment.py --input precip_series.tif --n-dates 12
    python drought-severity-assessment.py --bbox 116 39 117 40 --n-dates 12 --synthetic --output-dir ./out

License: MIT
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

VERSION = "1.0.0"
SKILL_NAME = "drought-severity-assessment"

# ---- 复用共享核心库（本地 vendored，随脚本目录一起分发）----
try:
    from _geoskill_core.errors import (
        GeoSkillError, UsageError, ValidationError, ProcessError, to_exit_code,
    )
    from _geoskill_core.manifest import OutputManifest, OutputFile
except ImportError:  # pragma: no cover - fallback minimal definitions
    class GeoSkillError(Exception):
        def __init__(self, message: str, code: int = 7, kind: str = "EGeo", **kw):
            super().__init__(message)
            self.message, self.code, self.kind = message, code, kind

    class UsageError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=2, kind="EUsage", **k)

    class ValidationError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=6, kind="EValidate", **k)

    class ProcessError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=7, kind="EProcess", **k)

    def to_exit_code(exc):
        return getattr(exc, "code", 7)

    OutputManifest = None
    OutputFile = None


# 干旱等级定义
DROUGHT_GRADES: Dict[int, str] = {
    0: "无旱",
    1: "轻旱",
    2: "中旱",
    3: "重旱",
    4: "特旱",
}


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def validate_bbox(bbox: List[float]) -> None:
    """Validate a [W, S, E, N] geographic bbox.

    Raises ValidationError (exit 6) on:
      - W >= E (or W > 180 or E > 180; allows E = 180 for antimeridian bounding)
      - S >= N
      - |lat| > 90 or |lon| > 180
      - zero area
      - bbox crosses the antimeridian (W < 0 with E > 180, or W > E in normal
        interpretation). For this skill we do NOT support wrap-around across
        the antimeridian; caller should split the bbox.
    """
    w, s, e, n = bbox
    if not all(np.isfinite([w, s, e, n])):
        raise ValidationError(
            f"bbox contains non-finite values: W={w} S={s} E={e} N={n}",
            bbox=list(bbox),
        )
    if abs(w) > 180.0 or abs(e) > 180.0:
        raise ValidationError(
            f"bbox longitude out of range: W={w} E={e} (must be in [-180, 180])",
            bbox=list(bbox),
        )
    if abs(s) > 90.0 or abs(n) > 90.0:
        raise ValidationError(
            f"bbox latitude out of range: S={s} N={n} (must be in [-90, 90])",
            bbox=list(bbox),
        )
    if w >= e:
        raise ValidationError(
            f"bbox reversed: W ({w}) must be < E ({e}). "
            f"For antimeridian-crossing bboxes, split into W..180 and -180..E.",
            bbox=list(bbox),
        )
    if s >= n:
        raise ValidationError(
            f"bbox reversed: S ({s}) must be < N ({n})", bbox=list(bbox)
        )
    if (e - w) < 1e-9 or (n - s) < 1e-9:
        raise ValidationError(
            f"bbox has zero area: W={w} S={s} E={e} N={n}", bbox=list(bbox)
        )


def validate_synthetic_params(n_dates: int) -> None:
    """Validate synthetic-mode parameters.

    n_dates must be >= 1 (synthetic has at least 1 time step; real input is
    unconstrained here). For the VHI component n_dates>=2 is required (we
    compare the last frame to the historical mean/std), but a 1-date
    synthetic falls back to a degenerate VHI of 0.
    """
    if not isinstance(n_dates, int) or n_dates < 1:
        raise ValidationError(
            f"--n-dates must be a positive integer, got {n_dates}",
            n_dates=n_dates,
        )


def read_geotiff_cube_with_nodata(
    path: str,
) -> Tuple[np.ndarray, List[float], int]:
    """Read a multi-band GeoTIFF, replacing NoData with NaN.

    Returns (cube_float32, bbox_WSEN, n_valid_pixels_per_band_count).
    The caller can use ``np.isfinite`` to identify valid pixels.
    Raises UsageError (exit 2) if file is missing.
    Raises ValidationError (exit 6) if all pixels are NoData in every band.
    """
    cube, bbox = read_geotiff_cube(path)
    # Apply NoData → NaN mask: rasterio's src.nodata is read inside
    # read_geotiff_cube, so we re-open to get it.
    import rasterio
    with rasterio.open(path) as src:
        nodata = src.nodata
    if nodata is not None:
        cube = np.where(cube == nodata, np.nan, cube).astype(np.float32)
    # Count valid pixels per band for diagnostics
    per_band_valid = int(np.sum(np.any(np.isfinite(cube), axis=0)))
    return cube, bbox, per_band_valid


# ---------------------------------------------------------------------------
# 核心算法：SPI
# ---------------------------------------------------------------------------
def fit_gamma_params(values: np.ndarray) -> Tuple[float, float, float]:
    """对降水样本拟合 Gamma 分布，返回 (shape, scale, p0)。

    p0 为零降水概率（混合分布中的离散零分量）。用 scipy.stats.gamma.fit
    并固定 loc=0（floc=0）。样本不足时回退到 (1, 1, p0)。
    """
    from scipy.stats import gamma

    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    total = arr.size
    if total == 0:
        return 1.0, 1.0, 0.0
    positive = arr[arr > 0]
    p0 = 1.0 - positive.size / total
    if positive.size < 2:
        return 1.0, 1.0, float(p0)
    shape, _loc, scale = gamma.fit(positive, floc=0)
    return float(shape), float(scale), float(p0)


def spi_from_precip(x: np.ndarray, params: Tuple[float, float, float]) -> np.ndarray:
    """将降水量（标量或数组）经 Gamma+正态反演转为 SPI。

    混合 CDF：F(x) = p0 + (1 − p0)·GammaCDF(x)（x > 0），x ≤ 0 时 F = p0。
    SPI = norm.ppf(F)，裁剪到 (1e-6, 1−1e-6) 以避免无穷。
    """
    from scipy.stats import gamma, norm

    shape, scale, p0 = params
    x = np.asarray(x, dtype=np.float64)
    cdf_pos = gamma.cdf(x, shape, scale=scale)
    cdf = np.where(x <= 0, p0, p0 + (1.0 - p0) * cdf_pos)
    cdf = np.clip(cdf, 1e-6, 1.0 - 1e-6)
    return norm.ppf(cdf).astype(np.float32)


def compute_spi_map(precip_cube: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """从 (n_dates, H, W) 降水立方体计算逐像元 SPI。

    用所有期次、所有像元的降水样本池拟合全局 Gamma 参数（保证样本充足、
    参数稳健），再对每个像元的全期平均降水量做 SPI 反演。
    """
    if precip_cube.ndim != 3:
        raise ValidationError(
            f"precip cube must be 3D (n_dates, H, W), got ndim={precip_cube.ndim}",
            ndim=int(precip_cube.ndim),
        )
    all_vals = precip_cube[np.isfinite(precip_cube)]
    if all_vals.size == 0:
        raise ValidationError("precipitation cube has no valid values")
    shape, scale, p0 = fit_gamma_params(all_vals)
    x = np.nanmean(precip_cube, axis=0)
    spi = spi_from_precip(x, (shape, scale, p0))
    info = {"gamma_shape": shape, "gamma_scale": scale, "p0_zero": p0,
            "n_dates": int(precip_cube.shape[0])}
    return spi, info


# ---------------------------------------------------------------------------
# 核心算法：VHI（植被健康指数）
# ---------------------------------------------------------------------------
def compute_vhi(ndvi_cube: np.ndarray) -> np.ndarray:
    """从 (n_dates, H, W) NDVI 立方体计算植被健康指数（NDVI 标准化距平）。

    VHI = (NDVI_当期 − NDVI_多年均值) / max(NDVI_标准差, 1e-3)。
    负值表示植被受胁迫（潜在干旱）。
    """
    if ndvi_cube.ndim != 3:
        raise ValidationError(
            f"NDVI cube must be 3D (n_dates, H, W), got ndim={ndvi_cube.ndim}",
            ndim=int(ndvi_cube.ndim),
        )
    mean = np.nanmean(ndvi_cube, axis=0)
    std = np.nanstd(ndvi_cube, axis=0)
    last = ndvi_cube[-1]
    vhi = (last - mean) / np.maximum(std, 1e-3)
    return vhi.astype(np.float32)


# ---------------------------------------------------------------------------
# 综合干旱分级
# ---------------------------------------------------------------------------
def classify_drought(
    spi: np.ndarray, vhi: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """将 SPI 与 VHI 合成为综合干旱指数并分级。

    两者均近似标准正态，等权平均得 drought_index，按阈值分级：
    ≥ −0.5 无旱；[−1.0, −0.5) 轻旱；[−1.5, −1.0) 中旱；
    [−2.0, −1.5) 重旱；< −2.0 特旱。

    返回 (grades uint8, drought_index float32)。
    """
    spi = np.asarray(spi, dtype=np.float32)
    if vhi is None:
        idx = spi
    else:
        vhi = np.asarray(vhi, dtype=np.float32)
        idx = 0.5 * spi + 0.5 * vhi
    grades = np.zeros(idx.shape, dtype=np.uint8)
    grades[idx < -0.5] = 1
    grades[idx < -1.0] = 2
    grades[idx < -1.5] = 3
    grades[idx < -2.0] = 4
    return grades, idx.astype(np.float32)


def drought_area_stats(
    grades: np.ndarray, pixel_area: float
) -> Dict[str, Any]:
    """统计各干旱等级的像元数与面积（m² / km²）。"""
    counts: Dict[str, int] = {}
    areas: Dict[str, float] = {}
    for k in range(5):
        n = int(np.count_nonzero(grades == k))
        counts[f"{k}_{DROUGHT_GRADES[k]}"] = n
        areas[f"{k}_{DROUGHT_GRADES[k]}_km2"] = float(n * pixel_area / 1e6)
    total = int(grades.size)
    drought_pix = int(np.count_nonzero(grades > 0))
    return {
        "grade_pixel_counts": counts,
        "grade_area_km2": areas,
        "total_pixels": total,
        "drought_pixels": drought_pix,
        "drought_fraction": float(drought_pix / total) if total else 0.0,
        "pixel_area_m2": float(pixel_area),
    }


def pixel_area_m2(bbox: List[float], height: int, width: int) -> float:
    """估算单个像元的地表面积（平方米）。"""
    w, s, e, n = bbox
    mid_lat = (s + n) / 2.0
    dx_m = (e - w) / max(width, 1) * 111320.0 * np.cos(np.deg2rad(mid_lat))
    dy_m = (n - s) / max(height, 1) * 110540.0
    return float(abs(dx_m * dy_m))


def run_drought(
    precip_cube: np.ndarray,
    ndvi_cube: Optional[np.ndarray],
    bbox: List[float],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """干旱评估主流程。

    返回 (grades, drought_index, spi, report_dict)。
    """
    spi, spi_info = compute_spi_map(precip_cube)
    if ndvi_cube is not None:
        vhi = compute_vhi(ndvi_cube)
        vhi_mean = float(np.mean(vhi))
    else:
        vhi = None
        vhi_mean = None
    grades, idx = classify_drought(spi, vhi)

    h, w = grades.shape
    pixel_area = pixel_area_m2(bbox, h, w)
    stats = drought_area_stats(grades, pixel_area)

    report: Dict[str, Any] = {
        "spi_params": spi_info,
        "spi_mean": float(np.mean(spi)),
        "spi_min": float(np.min(spi)),
        "vhi_mean": vhi_mean,
        "drought_index_mean": float(np.mean(idx)),
        "grade_names": DROUGHT_GRADES,
        "stats": stats,
    }
    return grades, idx, spi, report


# ---------------------------------------------------------------------------
# 合成数据：多期降水 + NDVI，部分区域干旱（离线测试）
# ---------------------------------------------------------------------------
def generate_synthetic(
    bbox: List[float],
    n_dates: int = 12,
    width: int = 128,
    height: int = 128,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """生成 (precip_cube, ndvi_cube, info)。

    背景：月降水约 100 mm，NDVI 约 0.6。右侧区域（xx > 0.62）在末期出现
    降水骤降（×0.25）+ NDVI 下降（至 ~0.25），模拟一场区域性气象—农业干旱。
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    yy = yy.astype(np.float32) / max(height - 1, 1)
    xx = xx.astype(np.float32) / max(width - 1, 1)

    base_precip = 110.0 - 30.0 * xx  # 空间梯度
    precip = np.zeros((n_dates, height, width), dtype=np.float32)
    for t in range(n_dates):
        field = base_precip + rng.normal(0, 18, size=(height, width)).astype(np.float32)
        precip[t] = np.clip(field, 0.0, None)

    # 末期右侧区域降水骤降
    drought_mask = xx > 0.62
    for t in range(max(0, n_dates - 3), n_dates):
        precip[t][drought_mask] *= 0.25

    # NDVI：背景 ~0.6，末期干旱区下降到 ~0.25
    ndvi = rng.uniform(0.55, 0.68, size=(n_dates, height, width)).astype(np.float32)
    low_ndvi = rng.uniform(0.20, 0.30, size=(height, width)).astype(np.float32)
    ndvi[-1, drought_mask] = low_ndvi[drought_mask]

    info = {
        "bbox": bbox, "n_dates": n_dates, "width": width, "height": height,
        "precip_mean": float(np.mean(precip)),
        "ndvi_mean": float(np.mean(ndvi)),
        "drought_region_fraction": float(np.mean(drought_mask)),
    }
    return precip, ndvi, info


# ---------------------------------------------------------------------------
# GeoTIFF I/O（直接用 rasterio，保证离线可用）
# ---------------------------------------------------------------------------
def write_geotiff(
    path: str,
    cube: np.ndarray,
    bbox: List[float],
    nodata: float = -9999.0,
    dtype: str = "float32",
) -> None:
    import rasterio
    from rasterio.transform import from_bounds

    if cube.ndim == 2:
        cube = cube[np.newaxis, ...]
    nb, h, w = cube.shape
    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], w, h)
    profile = {
        "driver": "GTiff", "height": h, "width": w, "count": nb,
        "dtype": dtype, "crs": "EPSG:4326", "transform": transform,
        "nodata": nodata, "compress": "deflate",
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        for b in range(nb):
            dst.write(cube[b].astype(dtype), b + 1)


def read_geotiff_cube(path: str) -> Tuple[np.ndarray, List[float]]:
    """读取多波段 GeoTIFF 为 (bands, H, W)。"""
    import rasterio
    if not os.path.exists(path):
        raise UsageError(f"input raster not found: {path}", path=path)
    with rasterio.open(path) as src:
        cube = src.read().astype(np.float32)
        b = src.bounds
        bbox = [b.left, b.bottom, b.right, b.top]
    return cube, bbox


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def write_manifest(
    output_dir: str,
    args: argparse.Namespace,
    outputs: List[Dict[str, Any]],
    qa: Dict[str, Any],
    started_at: str,
    exit_code: int,
    bbox: List[float],
) -> Optional[str]:
    if OutputManifest is None:
        return None
    cmd = " ".join([SKILL_NAME] + sys.argv[1:])
    man = OutputManifest(
        skill=SKILL_NAME,
        skill_version=VERSION,
        command=cmd,
        started_at=started_at,
        finished_at=_utc_now(),
        exit_code=exit_code,
        inputs={
            "input": getattr(args, "input", None),
            "n_dates": getattr(args, "n_dates", None),
            "synthetic": bool(getattr(args, "synthetic", False)),
        },
        outputs=[OutputFile(**o) for o in outputs],
        qa=qa,
        software={"python": sys.version.split()[0], "skill": SKILL_NAME},
    )
    path = os.path.join(output_dir, "output-manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def process(args: argparse.Namespace) -> int:
    started_at = _utc_now()
    output_dir = args.output_dir
    # bbox shape is validated up front (before any disk I/O or makedirs)
    bbox = list(args.bbox) if args.bbox else None
    if bbox is not None:
        validate_bbox(bbox)
    validate_synthetic_params(int(getattr(args, "n_dates", 12)))

    # 1) 获取数据
    synth_info: Optional[Dict[str, Any]] = None
    ndvi_cube: Optional[np.ndarray] = None
    if args.input and not args.synthetic:
        if not os.path.exists(args.input):
            raise UsageError(f"input raster not found: {args.input}", path=args.input)
        precip_cube, file_bbox, per_band_valid = read_geotiff_cube_with_nodata(args.input)
        if bbox is None:
            bbox = file_bbox
            validate_bbox(bbox)
        source_note = args.input
    else:
        if bbox is None:
            raise UsageError("provide --bbox (synthetic mode) or --input <raster>")
        precip_cube, ndvi_cube, synth_info = generate_synthetic(bbox, n_dates=args.n_dates)
        source_note = "synthetic"
        per_band_valid = int(np.sum(np.any(np.isfinite(precip_cube), axis=0)))

    if precip_cube.size == 0:
        raise ValidationError("precipitation data is empty")
    # 确保 3D（单波段输入扩展为 1 期）
    if precip_cube.ndim == 2:
        precip_cube = precip_cube[np.newaxis, ...]

    # NoData→NaN handling: if the input cube is 100 % NoData, fail loudly
    # instead of silently producing garbage SPI. ``np.isfinite`` correctly
    # excludes NaN; we need at least one finite pixel in any band to fit a
    # Gamma distribution.
    valid_mask_per_pixel = np.any(np.isfinite(precip_cube), axis=0)
    n_valid_pixels = int(valid_mask_per_pixel.sum())
    if n_valid_pixels == 0:
        raise ValidationError(
            "precipitation cube has no valid (non-NoData) pixels",
            n_valid_pixels=0,
            source=source_note,
        )

    # If the user passed a real GeoTIFF with NoData, also do in-place NaN
    # replacement (in synthetic mode the data is already clean; in real mode
    # the helper above already converted NoData to NaN). Belt-and-suspenders:
    # any leftover non-finite values become NaN.
    precip_cube = np.where(np.isfinite(precip_cube), precip_cube, np.nan).astype(np.float32)

    # Validate that there is at least 1 valid value per band so that the
    # temporal nanmean doesn't return NaN.
    valid_per_band = int(np.sum(np.any(np.isfinite(precip_cube), axis=(1, 2))))
    if valid_per_band == 0:
        raise ValidationError(
            "no precipitation values are finite after NoData masking",
            source=source_note,
        )

    # Now safe to create output directory
    os.makedirs(output_dir, exist_ok=True)

    # 2) 干旱评估
    grades, idx, spi, report = run_drought(precip_cube, ndvi_cube, bbox)

    # 3) 写出产物
    grade_tif = os.path.join(output_dir, "drought_grade.tif")
    spi_tif = os.path.join(output_dir, "spi.tif")
    write_geotiff(grade_tif, grades, bbox, nodata=255, dtype="uint8")
    write_geotiff(spi_tif, spi, bbox)

    report_path = os.path.join(output_dir, "drought_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    qa: Dict[str, Any] = {
        "source": source_note,
        "n_dates": int(precip_cube.shape[0]),
        "n_valid_pixels": n_valid_pixels,
        "n_total_pixels": int(precip_cube.shape[1] * precip_cube.shape[2]),
        "spi_mean": report["spi_mean"],
        "spi_min": report["spi_min"],
        "drought_fraction": report["stats"]["drought_fraction"],
        "grade_pixel_counts": report["stats"]["grade_pixel_counts"],
    }
    if synth_info is not None:
        qa["synthetic_drought_region_fraction"] = synth_info["drought_region_fraction"]

    outputs = [
        {"path": grade_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": spi_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": report_path, "kind": "json"},
    ]

    man_path = write_manifest(output_dir, args, outputs, qa, started_at, 0, bbox)

    if not args.quiet:
        print(f"[{SKILL_NAME}] source: {source_note}  n_dates: {precip_cube.shape[0]}")
        print(f"[{SKILL_NAME}] SPI mean: {report['spi_mean']:.3f}  min: {report['spi_min']:.3f}")
        print(f"[{SKILL_NAME}] drought fraction: {report['stats']['drought_fraction']*100:.1f}%")
        print(f"[{SKILL_NAME}] grade raster: {grade_tif}")
        print(f"[{SKILL_NAME}] spi raster:  {spi_tif}")
        if man_path:
            print(f"[{SKILL_NAME}] manifest: {man_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=SKILL_NAME,
        description="Combined drought grading fusing SPI (Gamma-fit) and VHI (NDVI anomaly).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                   help="geographic extent [minLon minLat maxLon maxLat]")
    p.add_argument("--input", help="input multi-band precipitation GeoTIFF (band = date)")
    p.add_argument("--n-dates", type=int, default=12,
                   help="number of time steps for synthetic mode (default: 12)")
    p.add_argument("--synthetic", action="store_true",
                   help="generate a physics-consistent synthetic dataset (offline)")
    p.add_argument("--output-dir", default="./output", help="output directory")
    p.add_argument("--quiet", action="store_true", help="suppress console output")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return process(args)
    except GeoSkillError as exc:
        print(f"[{SKILL_NAME}] ERROR [{exc.kind}] {exc.message}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[{SKILL_NAME}] ERROR {exc}", file=sys.stderr)
        return to_exit_code(exc)


if __name__ == "__main__":
    sys.exit(main())
