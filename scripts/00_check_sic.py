#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
00_check_sic.py —— 诊断脚本（只读、只打印，不写任何文件）

为什么要它
    02_sept_sie.py 跑出的 9 月 SIE 是 5.28（1979）… 3.66（2007）×10⁶ km²，
    比文献的 Bootstrap 值（约 7.1 … 4.6）系统性偏低 20–25%，且低冰年偏低更多。
    在改口径之前，先分清是下面哪一种：

      (甲) 冰边缘被"稀释"：浓度场里 0–15% 的过渡带被重采样拉宽，
           15% 阈值的内缩 —— 表现为 SIE(0.1%) 远大于 SIE(15%)，且 5–15% 档面积大。
      (乙) 冰边缘被"抹掉"：边缘格点重采样成 -999 —— 表现为各阈值下 SIE 都小，
           且高纬带缺测比例异常高。
      (丙) 数据本身不是这个时段的浓度（单位/变量搞错）—— 表现为直方图不像海冰。

打印内容
    A. regrid 文件（1°）：缺测的纬度分布、浓度分档面积、SIE 对阈值的敏感性、SIA
    B. 备选 25 km 文件：结构（维、变量、属性、时间单位、经纬网格），
       供下一步决定是否换回原生网格（对应 decisions.md 的 Q3）

用法
    /usr/bin/python3 scripts/00_check_sic.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import xarray as xr

REGRID = Path("/SSD1/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc")
NATIVE = Path("/SSD1/SST_SIC/sic_psn25_197811-202412_v05r00.nc")

YEARS = [1979, 1987, 1996, 2007, 2009]
THRESHOLDS = [0.1, 1.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0]
BINS = [0.0, 5.0, 15.0, 30.0, 50.0, 75.0, 90.0, 100.0]
R = 6371.0


def banner(t):
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


def area_1deg(lat, lon):
    dlat = np.abs(np.diff(lat)).mean()
    dlon = np.abs(np.diff(lon)).mean()
    hi = np.clip(lat + dlat / 2, -90, 90)
    lo = np.clip(lat - dlat / 2, -90, 90)
    dsin = np.abs(np.sin(np.deg2rad(hi)) - np.sin(np.deg2rad(lo)))
    a1 = R ** 2 * np.deg2rad(dlon) * dsin
    return np.repeat(a1[:, None], lon.size, axis=1)


def decode_ym(raw, units):
    m = re.match(r"\s*(\w+)\s+since\s+(\d{4})-(\d{1,2})-(\d{1,2})", units)
    step, y0, m0 = m.group(1), int(m.group(2)), int(m.group(3))
    if step != "months":
        raise ValueError(f"本诊断只处理 months since，实际 {units!r}")
    ym = y0 * 12 + (m0 - 1) + np.asarray(raw, dtype="int64")
    return ym // 12, ym % 12 + 1


def part_a():
    banner("A. regrid 文件（1°×1°，双线性重采样）")
    ds = xr.open_dataset(REGRID, decode_times=False)
    try:
        ice = ds["ice"]
        lat = np.asarray(ds["lat"].values, float)
        lon = np.asarray(ds["lon"].values, float)
        years, months = decode_ym(ds["time"].values, ds["time"].attrs["units"])
        print(f"形状 {tuple(ice.shape)}；lat {lat.min():g}…{lat.max():g}；"
              f"lon {lon.min():g}…{lon.max():g}")
        print(f"时间 {years[0]}-{months[0]:02d} … {years[-1]}-{months[-1]:02d}")

        area = area_1deg(lat, lon)
        north = lat > 0
        a = np.where(north[:, None], area, 0.0)          # 南半球权重置 0

        # --- 缺测的纬度分布（取 1979-09）---
        i0 = int(np.where((years == 1979) & (months == 9))[0][0])
        v0 = np.asarray(ice.isel(time=i0).values, float)
        miss = ~np.isfinite(v0)
        bands = [(60, 70), (70, 80), (80, 90)]
        print("\n[缺测纬度分布 1979-09]，按 1° 带统计：")
        for lo, hi in bands:
            m = (lat >= lo) & (lat < hi) if hi < 90 else (lat >= lo) & (lat <= 90)
            tot = a[m, :].sum() / 1e6
            mm = a[m, :][miss[m, :]].sum() / 1e6
            print(f"  {lo:>2}–{hi:<2}°N : 带宽面积 {tot:7.2f}×10⁶ km²，"
                  f"缺测 {mm:7.2f}（{mm / tot * 100 if tot else 0:5.1f}%）")

        # --- 逐年：阈值敏感性 + 浓度分档 ---
        for y in YEARS:
            k = np.where((years == y) & (months == 9))[0]
            if k.size == 0:
                print(f"\n{y}-09：数据里没有，跳过")
                continue
            v = np.asarray(ice.isel(time=int(k[0])).values, float) * 100.0
            ok = np.isfinite(v)
            vv = np.where(ok, v, 0.0)

            print(f"\n{y}-09  北极有效格点面积 {(a * ok).sum() / 1e6:.2f}×10⁶ km²")
            print("   阈值(%) → SIE(×10⁶ km²):  " + "  ".join(
                f"{t:>4g}:{((vv > t) * a).sum() / 1e6:5.2f}" for t in THRESHOLDS))
            print(f"   SIA（浓度加权）= {(vv / 100.0 * a).sum() / 1e6:.2f}×10⁶ km²")
            print("   浓度分档面积(×10⁶ km²):  " + "  ".join(
                f"{BINS[j]:g}–{BINS[j + 1]:g}%:"
                f"{(((vv >= BINS[j]) & (vv < BINS[j + 1])) * a).sum() / 1e6:5.2f}"
                for j in range(len(BINS) - 1)))
    finally:
        ds.close()


def part_b():
    banner("B. 备选文件 sic_psn25_197811-202412_v05r00.nc 的结构")
    if not NATIVE.is_file():
        print(f"文件不存在：{NATIVE}")
        return
    with xr.open_dataset(NATIVE, decode_times=False) as ds:
        print("维度:", {k: v for k, v in ds.sizes.items()})
        print("变量:", list(ds.variables))
        for name, var in ds.variables.items():
            print(f"\n[{name}] dims={var.dims} shape={var.shape} dtype={var.dtype}")
            for k, val in var.attrs.items():
                s = str(val)
                print(f"    {k} = {s[:110]}{'…' if len(s) > 110 else ''}")
        # 经纬度是 1D 还是 2D、范围多少
        for cand in ("lat", "latitude", "Latitude"):
            if cand in ds.variables:
                a = np.asarray(ds[cand].values, float)
                print(f"lat[{cand}] ndim={a.ndim} 范围 {np.nanmin(a):.2f}…{np.nanmax(a):.2f}")
        for cand in ("lon", "longitude", "Longitude"):
            if cand in ds.variables:
                a = np.asarray(ds[cand].values, float)
                print(f"lon[{cand}] ndim={a.ndim} 范围 {np.nanmin(a):.2f}…{np.nanmax(a):.2f}")
        for cand in ("time",):
            if cand in ds.variables and ds[cand].size:
                raw = np.asarray(ds[cand].values)
                print(f"time 原始值 {raw.min()}…{raw.max()}，units={ds[cand].attrs.get('units')}")


def main():
    print("诊断：02 的 SIE 为何比文献低 20–25%")
    part_a()
    part_b()
    print("\n判读：")
    print("  SIE(0.1%) >> SIE(15%) 且 5–15% 档面积大  → (甲) 边缘被稀释")
    print("  各阈值下 SIE 都小、70–90°N 缺测比例高     → (乙) 边缘被抹掉")
    print("  两者都不明显                             → (丙) 数据/单位层面有问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
