"""Core algorithm tests for drought-severity-assessment."""
import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import mod as dr


class TestFitGamma:
    def test_recovers_gamma_params(self):
        """从 Gamma(2, scale=3) 样本拟合，shape/scale 应接近真值。"""
        rng = np.random.default_rng(0)
        samples = rng.gamma(shape=2.0, scale=3.0, size=5000)
        shape, scale, p0 = dr.fit_gamma_params(samples)
        assert abs(shape - 2.0) < 0.3
        assert abs(scale - 3.0) < 0.6
        assert p0 == 0.0

    def test_zero_fraction(self):
        vals = np.array([0.0, 0.0, 5.0, 10.0, 15.0])
        _, _, p0 = dr.fit_gamma_params(vals)
        assert abs(p0 - 0.4) < 1e-9

    def test_empty(self):
        shape, scale, p0 = dr.fit_gamma_params(np.array([]))
        assert shape == 1.0 and scale == 1.0 and p0 == 0.0


class TestSPI:
    def test_spi_standard_normal_property(self):
        """对同分布 Gamma 样本做 SPI 变换，结果应近似标准正态（均值~0, 标准差~1）。"""
        rng = np.random.default_rng(1)
        samples = rng.gamma(shape=2.0, scale=2.0, size=20000).astype(np.float64)
        params = dr.fit_gamma_params(samples)
        spi = dr.spi_from_precip(samples, params)
        assert abs(float(np.mean(spi))) < 0.05
        assert abs(float(np.std(spi)) - 1.0) < 0.05

    def test_spi_monotonic_in_precip(self):
        """降水越多，SPI 越大（越湿）。"""
        params = (2.0, 2.0, 0.0)
        x = np.array([0.5, 2.0, 5.0, 10.0])
        spi = dr.spi_from_precip(x, params)
        assert np.all(np.diff(spi) > 0)

    def test_spi_dry_negative(self):
        """远低于均值的降水 → SPI < 0（偏干）。"""
        rng = np.random.default_rng(2)
        samples = rng.gamma(2.0, 2.0, 3000)
        params = dr.fit_gamma_params(samples)
        spi_low = dr.spi_from_precip(np.array([0.2]), params)
        spi_high = dr.spi_from_precip(np.array([20.0]), params)
        assert spi_low[0] < 0
        assert spi_high[0] > 0

    def test_spi_finite(self):
        params = (2.0, 2.0, 0.1)
        spi = dr.spi_from_precip(np.array([0.0, 1.0, 100.0]), params)
        assert np.isfinite(spi).all()


class TestComputeSPIMap:
    def test_shape(self):
        rng = np.random.default_rng(3)
        cube = rng.gamma(2.0, 20.0, size=(12, 16, 16)).astype(np.float32)
        spi, info = dr.compute_spi_map(cube)
        assert spi.shape == (16, 16)
        assert info["n_dates"] == 12

    def test_bad_ndim_raises(self):
        with pytest.raises(dr.ValidationError):
            dr.compute_spi_map(np.zeros((10, 10)))


class TestVHI:
    def test_negative_anomaly_gives_negative_vhi(self):
        """末期 NDVI 低于多年均值 → VHI < 0。"""
        cube = np.full((12, 4, 4), 0.6, dtype=np.float32)
        cube[-1] = 0.2  # 末期骤降
        vhi = dr.compute_vhi(cube)
        assert (vhi < 0).all()

    def test_positive_anomaly(self):
        cube = np.full((12, 4, 4), 0.5, dtype=np.float32)
        cube += np.random.default_rng(4).normal(0, 0.02, cube.shape).astype(np.float32)
        cube[-1] = 0.8  # 末期偏高
        vhi = dr.compute_vhi(cube)
        assert (vhi > 0).all()

    def test_bad_ndim_raises(self):
        with pytest.raises(dr.ValidationError):
            dr.compute_vhi(np.zeros((5, 5)))


class TestClassifyDrought:
    def test_thresholds(self):
        spi = np.array([[0.0, -0.7, -1.2, -1.7, -2.5]], dtype=np.float32)
        grades, idx = dr.classify_drought(spi)
        assert grades[0, 0] == 0  # 无旱
        assert grades[0, 1] == 1  # 轻旱
        assert grades[0, 2] == 2  # 中旱
        assert grades[0, 3] == 3  # 重旱
        assert grades[0, 4] == 4  # 特旱

    def test_vhi_worsens_drought(self):
        """同样 SPI，叠加负 VHI 后干旱等级不降低。"""
        spi = np.array([[-0.8]], dtype=np.float32)
        g_no, _ = dr.classify_drought(spi)
        g_vhi, _ = dr.classify_drought(spi, vhi=np.array([[-1.5]], dtype=np.float32))
        assert g_vhi[0, 0] >= g_no[0, 0]


class TestDroughtAreaStats:
    def test_counts(self):
        grades = np.array([[0, 0, 1], [2, 3, 4]], dtype=np.uint8)
        stats = dr.drought_area_stats(grades, pixel_area=1e6)
        assert stats["total_pixels"] == 6
        assert stats["drought_pixels"] == 4
        assert abs(stats["drought_fraction"] - 4 / 6) < 1e-9


class TestRunDroughtSynthetic:
    def test_detects_drought_region(self):
        """合成数据的干旱区（右侧）应被检测出高于背景的干旱等级。"""
        bbox = [116, 39, 117, 40]
        precip, ndvi, info = dr.generate_synthetic(bbox, n_dates=12, seed=7)
        grades, idx, spi, report = dr.run_drought(precip, ndvi, bbox)
        h, w = grades.shape
        left = grades[:, : w // 4]
        right = grades[:, -w // 4:]
        assert float(np.mean(right)) > float(np.mean(left))
        assert report["stats"]["drought_pixels"] > 0

    def test_spi_mean_near_zero(self):
        """全局 SPI 均值应接近 0（标准正态性质）。"""
        precip, ndvi, _ = dr.generate_synthetic([116, 39, 117, 40], n_dates=12, seed=11)
        spi, _ = dr.compute_spi_map(precip)
        assert abs(float(np.mean(spi))) < 0.5


class TestGeoTiffIO:
    def test_roundtrip(self, tmp_path):
        arr = np.random.uniform(-3, 3, (20, 20)).astype(np.float32)
        bbox = [116.0, 39.0, 117.0, 40.0]
        path = str(tmp_path / "spi.tif")
        dr.write_geotiff(path, arr, bbox)
        assert os.path.exists(path)
        back, rbbox = dr.read_geotiff_cube(path)
        assert back.shape == (1, 20, 20)
        np.testing.assert_allclose(rbbox, bbox, atol=1e-6)
        np.testing.assert_allclose(back[0], arr, atol=1e-4)

    def test_read_missing_raises(self):
        with pytest.raises(dr.UsageError):
            dr.read_geotiff_cube("/nonexistent/nope.tif")
