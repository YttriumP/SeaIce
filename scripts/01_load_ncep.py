#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_load_ncep.py —— 读 NCEP/NCAR R1 的 925 hPa 月平均 u/v，切 1979–2009

目的
    复现 Ogi et al. (2010) 的第 0 步：把 925 hPa 月平均风场读进来，锁定层次，
    切出 1979-01 至 2009-12（含首尾，共 372 个月，其中 31 个 9 月），
    落一个中间文件给后续 03_seasonal_wind.py 用。
    本脚本**不做**季节平均、不做回归、不做去气候态——那些是后面脚本的事。

输入（只读，禁止写入/删除/移动）
    /SSD1/NCEP1/uwnd.mon.mean.nc     变量 uwnd(time, level, lat, lon)，单位 m/s
    /SSD1/NCEP1/vwnd.mon.mean.nc     变量 vwnd，同上
    （/data/NCEP1 是 /SSD1 的软链接；按 AGENTS.md「优先 /SSD1」，先找 /SSD1，找不到才退回 /data，
      两条路径都会打印实际用了哪一条，不静默替换）

输出
    out/ncep925_uv_1979_2009.nc      u(time, lat, lon)、v(time, lat, lon)，925 hPa
                                     约 31 MB；属性里记了源路径与口径，不含时间戳，重跑字节一致

依赖
    xarray + numpy + netcdf4。缺库时先建虚拟环境：
        python3 -m venv .venv
        .venv/bin/pip install -U xarray numpy netcdf4
        .venv/bin/python scripts/01_load_ncep.py

口径（glossary.md §5）
    层次 925 hPa、月平均、1979–2009 含首尾。925 hPa 用**坐标值**选取，不写死层索引。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import numpy as np
    import xarray as xr
except ImportError as exc:  # pragma: no cover - 仅用于给出人话提示
    sys.exit(
        f"缺少依赖: {exc.name}\n"
        "建议在项目根建虚拟环境后安装:\n"
        "    python3 -m venv .venv\n"
        "    .venv/bin/pip install -U xarray numpy netcdf4\n"
        "    .venv/bin/python scripts/01_load_ncep.py"
    )

# ---------------------------------------------------------------------------
# 口径常量：改这里 = 改口径 = 作废（见 glossary.md §5）
# ---------------------------------------------------------------------------
LEVEL_HPA = 925.0                                     # 目标层次（hPa）
YEAR_START, YEAR_END = 1979, 2009                     # 复现时段，含首尾
N_MONTH_EXPECTED = (YEAR_END - YEAR_START + 1) * 12   # 372
N_SEP_EXPECTED = YEAR_END - YEAR_START + 1            # 31 个 9 月
TIME_SLICE = (f"{YEAR_START}-01-01", f"{YEAR_END}-12-31")

# 数据只读；优先 SSD，退回机械盘
DATA_DIRS = [Path("/SSD1/NCEP1"), Path("/data/NCEP1")]
FILE_U, FILE_V = "uwnd.mon.mean.nc", "vwnd.mon.mean.nc"

# 项目根由 __file__ 推导，不写死 /home/gst/lcx
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "out"
OUT_NC = OUT_DIR / "ncep925_uv_1979_2009.nc"

ABS_MAX_WIND = 150.0   # 风场量级自检上限（m/s），NCEP 月平均 925 hPa 远小于此
HUGE = 1.0e30          # 未解码的 _FillValue 常见为 ±9.96921e36，用这个阈值兜底


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def resolve_data_dir() -> Path:
    """定位数据目录：先 /SSD1 后 /data，必须两个文件都在。"""
    for d in DATA_DIRS:
        if (d / FILE_U).is_file() and (d / FILE_V).is_file():
            tag = "（/data 软链接，物理在 SSD）" if str(d).startswith("/data") else "（NVMe）"
            print(f"[路径] 数据目录 = {d} {tag}")
            return d
    tried = "、".join(str(d) for d in DATA_DIRS)
    raise FileNotFoundError(
        f"找不到 {FILE_U} 或 {FILE_V}，已尝试：{tried}（数据盘只读，请确认挂载）"
    )


def open_dataset_robust(path: Path) -> xr.Dataset:
    """
    打开数据集。NCEP1 的 time:units 是 "hours since 1800-01-01 00:00:0.0"，
    这个 "00:00:0.0" 写法在某些版本的 CF 解码器里会解析失败，
    失败时退回 decode_times=False，自己按 units 换算，保证脚本不会因为时间轴而死。
    """
    try:
        return xr.open_dataset(path)
    except Exception as exc:  # noqa: BLE001 - 只有一个目的：别让时间解码挡住读数据
        print(f"[时间] 标准 CF 解码失败（{type(exc).__name__}: {exc}）")
        print("[时间] 退回手工解码 time（decode_times=False）")
        ds = xr.open_dataset(path, decode_times=False)
        raw = ds["time"]
        units = str(raw.attrs.get("units", "")).strip()
        m = re.match(r"(seconds|hours|days)\s+since\s+(\d{4})-(\d{2})-(\d{2})", units)
        if not m:
            raise ValueError(f"无法解析 time:units = {units!r}") from exc
        step, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        factor = {"seconds": 1, "hours": 3600, "days": 86400}[step]
        t0 = np.datetime64(f"{y:04d}-{mo:02d}-{d:02d}", "s")
        new_t = t0 + (np.asarray(raw.values, dtype="float64") * factor).astype("timedelta64[s]")
        ds = ds.assign_coords(time=("time", new_t))
        ds["time"].attrs["units"] = units
        return ds


def level_values_hpa(da: xr.DataArray) -> np.ndarray:
    """把 level 坐标换算成 hPa。NCEP1 的 units 是 millibar，这里留 Pa 的兜底。"""
    lev = np.asarray(da["level"].values, dtype=float)
    units = str(da["level"].attrs.get("units", "")).strip().lower()
    if units in {"pa", "pascal", "pascals"}:
        lev = lev / 100.0
        print("[层] 源文件 level 单位为 Pa，已 /100 换算为 hPa")
    return lev


def load_wind(path: Path, varname: str) -> tuple[xr.DataArray, dict]:
    """打开单个风场文件，返回 925 hPa 的 DataArray（时间未切片，已载入内存）与自检信息。"""
    ds = open_dataset_robust(path)
    try:
        if varname not in ds:
            raise KeyError(f"{path.name} 里没有变量 {varname}，实际变量: {list(ds.data_vars)}")

        da = ds[varname]
        units = str(da.attrs.get("units", "")).strip()
        if units != "m/s":
            raise ValueError(f"{varname} 单位是 {units!r}，期望 'm/s'，口径不对，停下")
        if "level" not in da.dims:
            raise ValueError(f"{varname} 没有 level 维（dims={da.dims}），这不是多层月平均场")

        lev_hpa = level_values_hpa(da)
        dist = np.abs(lev_hpa - LEVEL_HPA)
        idx = int(np.argmin(dist))
        if dist[idx] > 0.5:
            raise ValueError(
                f"层表里没有 {LEVEL_HPA} hPa，最近的是 {lev_hpa[idx]} hPa；"
                f"可用层: {np.array2string(lev_hpa, precision=1)}"
            )

        # 索引是**算出来的**，不是写死的常量；取完把维度压掉，保留标量坐标便于溯源
        da925 = da.isel(level=idx, drop=True).squeeze(drop=True)
        da925 = da925.assign_coords(level_hpa=float(lev_hpa[idx]))
        da925.attrs = dict(da.attrs)
        da925.attrs["level_hpa"] = float(lev_hpa[idx])
        # 显式载入内存：后面会关掉文件句柄，不能让 DataArray 继续懒加载
        da925 = da925.load()

        info = {
            "file": str(path),
            "varname": varname,
            "raw_shape": tuple(int(s) for s in da.shape),
            "raw_dims": tuple(da.dims),
            "level_table_hpa": lev_hpa,
            "level_index": idx,
            "level_used_hpa": float(lev_hpa[idx]),
            "time_start": str(da.time.values[0])[:19],
            "time_end": str(da.time.values[-1])[:19],
            "n_time_raw": int(da.sizes["time"]),
            "dtype": str(da.dtype),
        }
    finally:
        ds.close()
    return da925, info


def mask_and_count_fill(da: xr.DataArray, label: str) -> tuple[xr.DataArray, int]:
    """统计缺测：xarray 默认已把 _FillValue 解成 NaN，这里再兜一层未解码的大数。"""
    v = da.values
    if np.issubdtype(v.dtype, np.floating):
        n_nan = int(np.isnan(v).sum())
        n_huge = int((np.abs(v) > HUGE).sum())
    else:
        n_nan, n_huge = 0, 0
    if n_huge:
        print(f"[缺测] {label}: 发现 {n_huge} 个未解码的 _FillValue 量级大数，已转成 NaN")
        da = da.where(np.abs(da) < HUGE)

    total = n_nan + n_huge
    if total:
        print(f"[缺测] {label}: NaN = {total} 个，占 {total / da.size * 100:.4f}%")
    else:
        print(f"[缺测] {label}: 0 个")
    return da, total


def check_time_axis(sub: xr.DataArray, label: str) -> int:
    """检查时间轴：单调、逐月连续、无重复；返回 9 月个数。"""
    t = sub.indexes["time"]
    years = np.asarray(sub.time.dt.year.values)
    months = np.asarray(sub.time.dt.month.values)
    ym = years * 12 + (months - 1)

    if not t.is_monotonic_increasing:
        raise ValueError(f"{label} 时间轴不是单调递增")
    if np.unique(ym).size != ym.size:
        raise ValueError(f"{label} 时间轴有重复月份")
    if np.any(np.diff(ym) != 1):
        gaps = np.where(np.diff(ym) != 1)[0]
        raise ValueError(f"{label} 时间轴不连续，断点 {len(gaps)} 处，首处位于索引 {gaps[0]}")

    n_sep = int(np.sum(months == 9))
    print(f"[时间] {label}: {str(sub.time.values[0])[:7]} → {str(sub.time.values[-1])[:7]}，"
          f"{sub.sizes['time']} 个月，逐月连续")
    print(f"[时间] {label}: 其中 9 月 {n_sep} 个（期望 {N_SEP_EXPECTED}）")
    return n_sep


def write_netcdf(ds: xr.Dataset, path: Path) -> None:
    """写 NetCDF4；netcdf4 引擎缺失时退回 h5netcdf，再不行让 xarray 自己挑。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    attempts = [("netcdf4", "NETCDF4"), ("h5netcdf", "NETCDF4"), (None, None)]
    last_exc: Exception | None = None
    for engine, fmt in attempts:
        try:
            if engine is None:
                ds.to_netcdf(path, mode="w")
            else:
                ds.to_netcdf(path, mode="w", engine=engine, format=fmt)
            print(f"[输出] 写出 {path}（engine={engine or 'auto'}，"
                  f"{path.stat().st_size / 1e6:.1f} MB）")
            return
        except Exception as exc:  # noqa: BLE001 - 引擎不可用就换下一个
            last_exc = exc
            print(f"[输出] engine={engine} 写入失败（{type(exc).__name__}: {exc}），换下一个")
    raise RuntimeError(f"写 NetCDF 失败，最后一个错误: {last_exc}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    banner("01_load_ncep.py | NCEP/NCAR R1 925 hPa 月平均 u/v，1979–2009")

    data_dir = resolve_data_dir()
    u925, info_u = load_wind(data_dir / FILE_U, "uwnd")
    v925, info_v = load_wind(data_dir / FILE_V, "vwnd")

    for name, da, info in (("u", u925, info_u), ("v", v925, info_v)):
        print(f"\n[{name}] 文件 = {info['file']}")
        print(f"[{name}] 原始维序/形状 = {info['raw_dims']} {info['raw_shape']}，dtype={info['dtype']}")
        print(f"[{name}] 原始时间 = {info['time_start']} → {info['time_end']}（{info['n_time_raw']} 个月）")
        print(f"[{name}] 层表(hPa) = {np.array2string(info['level_table_hpa'], precision=1)}")
        print(f"[{name}] 选中层: index={info['level_index']}，level={info['level_used_hpa']:g} hPa，"
              f"取后形状={tuple(da.shape)}")

    if tuple(u925.shape) != tuple(v925.shape):
        raise ValueError(f"u 与 v 形状不一致: {u925.shape} vs {v925.shape}")
    if not np.array_equal(u925.time.values, v925.time.values):
        raise ValueError("u 与 v 时间轴不一致（其中一个被回溯更新过？）")

    # ---- 时间切片：1979-01 至 2009-12，含首尾 ----
    u = u925.sel(time=slice(*TIME_SLICE))
    v = v925.sel(time=slice(*TIME_SLICE))
    if u.sizes["time"] != N_MONTH_EXPECTED:
        raise ValueError(f"切片后 {u.sizes['time']} 个月，期望 {N_MONTH_EXPECTED} 个")

    n_sep = check_time_axis(u, "u/v 切片结果")
    assert n_sep == N_SEP_EXPECTED, f"9 月个数 {n_sep} != {N_SEP_EXPECTED}，时段口径不对"

    # ---- 缺测统计（切片之后统计，这才是后面真正用的场）----
    u, n_miss_u = mask_and_count_fill(u, "u(925hPa)")
    v, n_miss_v = mask_and_count_fill(v, "v(925hPa)")

    # ---- 物理量级硬约束 ----
    for name, da in (("u", u), ("v", v)):
        with np.errstate(invalid="ignore"):
            amax = float(np.nanmax(np.abs(da.values)))
            amean = float(np.nanmean(da.values))
        print(f"[量级] {name}: |max| = {amax:.2f} m/s，mean = {amean:.3f} m/s")
        if not np.isfinite(amax) or amax > ABS_MAX_WIND:
            raise ValueError(f"{name} 的 |max| = {amax} m/s 超出合理范围，数据可能损坏")

    if max(n_miss_u, n_miss_v) == 0:
        print("\n[缺测] 925 hPa 切片后无缺测")
    else:
        # TODO(待确认): 若真出现缺测，需人工看缺测格点落在哪（青藏高原地形附近 vs 北极），
        #               再决定能否直接往下用；复现阶段不插值、不填补。
        print(f"\n[缺测] 存在缺测（u {n_miss_u} / v {n_miss_v}），复现阶段不插值，请人工确认")

    # ---- 写产物 ----
    ds_out = xr.Dataset(
        {"u": u.astype("float32"), "v": v.astype("float32")},
        attrs={
            "title": "NCEP/NCAR Reanalysis 1 monthly mean wind at 925 hPa, 1979-2009",
            "source_u": f"{data_dir / FILE_U} :: uwnd",
            "source_v": f"{data_dir / FILE_V} :: vwnd",
            "level_hpa": f"{LEVEL_HPA:g}",
            "time_coverage": f"{str(u.time.values[0])[:7]} to {str(u.time.values[-1])[:7]} inclusive",
            "n_months": str(u.sizes["time"]),
            "n_septembers": str(n_sep),
            "missing_policy": "FillValue -> NaN, no interpolation",
            "units": "m/s",
            "reference": "Kalnay et al. (1996); Kistler et al. (2001)",
            "note": "step 1 of the Ogi et al. (2010) reproduction; seasonal averaging NOT applied",
        },
    )
    ds_out["level_hpa"].attrs.update({"units": "hPa", "long_name": "pressure level"})
    write_netcdf(ds_out, OUT_NC)

    # ---- 回读验证：写出去的和内存里的是否一致 ----
    with xr.open_dataset(OUT_NC) as chk:
        if chk.sizes["time"] != N_MONTH_EXPECTED:
            raise AssertionError("回读时间长度不对")
        if set(chk.data_vars) != {"u", "v"}:
            raise AssertionError("回读变量名不对")
        for name in ("u", "v"):
            if not np.allclose(chk[name].values, ds_out[name].values, equal_nan=True):
                raise AssertionError(f"回读的 {name} 与写入的不一致")
    print("[回读] u/v 与内存中一致，时间长度与变量名正确")

    banner("自检汇总")
    print(f"层索引(算出来的) : {info_u['level_index']}  →  level = {info_u['level_used_hpa']:g} hPa")
    print(f"原始形状         : {info_u['raw_shape']}  (time, level, lat, lon)")
    print(f"切片后形状       : {tuple(u.shape)}  (time, lat, lon)")
    print(f"时间范围         : {str(u.time.values[0])[:7]} → {str(u.time.values[-1])[:7]}（含首尾）")
    print(f"月数 / 9 月数    : {u.sizes['time']} / {n_sep}")
    print(f"缺测             : u={n_miss_u}, v={n_miss_v}")
    print(f"纬度             : {float(u.lat[0]):g} → {float(u.lat[-1]):g}，{u.sizes['lat']} 格（2.5°）")
    print(f"经度             : {float(u.lon[0]):g} → {float(u.lon[-1]):g}，{u.sizes['lon']} 格（2.5°）")
    print(f"产物             : {OUT_NC}")
    print("\n[完成] 01_load_ncep.py 正常结束。下一步：02_sept_sie.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
