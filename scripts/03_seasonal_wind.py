#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_seasonal_wind.py —— 925 hPa 风场的 JFMAM / JJAS 季节平均与异常场

目的
    把 01 输出（1979–2009 月平均 u/v）压成两个季节序列，供 04 做"风场对 9 月 SIE 回归"：
        冬 = JFMAM（1–5 月平均，**不跨年**）
        夏 = JJAS （6–9 月平均，**不跨年**）
    同时算出 31 年的季节气候态并减掉，得到异常场（后面投影、回归都用异常场）。

输入
    out/ncep925_uv_1979_2009.nc      （01_load_ncep.py 的产物，372 个月）

输出
    out/wind_seasonal_1979_2009.nc
        year(31), lat(73), lon(144)
        u_win, v_win, u_sum, v_sum          季节平均（原始场）
        ua_win, va_win, ua_sum, va_sum      相对 31 年季节气候态的异常

依赖
    xarray + numpy（服务器 /usr/bin/python3 已含）

口径（glossary.md §5，不要改）
    冬 JFMAM、夏 JJAS，**都不跨年**：1979 年的冬 = 1979 年 1–5 月，1979 年的夏 = 1979 年 6–9 月。
    所以 1979–2009 各 31 个冬、31 个夏，没有"缺第一个冬天"的问题。
    注意 JJAS 含 9 月，与预报对象（9 月 SIE）同期；这是原文的口径，不是笔误。

未决（留给 04/05/06，不在本脚本里定）
    - 回归时 SIE 用原始值还是标准化值（影响系数量级，不影响 R²）
    - 投影权重是否乘 cos(lat)（reproduction_plan.md 风险表）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

# ---------------------------------------------------------------------------
# 口径常量
# ---------------------------------------------------------------------------
YEAR_START, YEAR_END = 1979, 2009
WINTER_MONTHS = (1, 2, 3, 4, 5)      # JFMAM
SUMMER_MONTHS = (6, 7, 8, 9)         # JJAS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_NC = PROJECT_ROOT / "out" / "ncep925_uv_1979_2009.nc"
OUT_NC = PROJECT_ROOT / "out" / "wind_seasonal_1979_2009.nc"


def banner(t: str) -> None:
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


def season_mean(u: xr.DataArray, months: tuple[int, ...], label: str) -> xr.DataArray:
    """
    逐年做季节平均，dim=year。缺任何一个月就报错（不静默跳过、不补插）。
    """
    years = np.asarray(u.time.dt.year.values)
    mons = np.asarray(u.time.dt.month.values)
    out = []
    for y in range(YEAR_START, YEAR_END + 1):
        sel = (years == y) & np.isin(mons, months)
        if int(sel.sum()) != len(months):
            raise ValueError(
                f"{label} {y} 年只找到 {int(sel.sum())} 个月（期望 {len(months)}），"
                f"缺月份，检查 01 的切片"
            )
        out.append(u.isel(time=np.where(sel)[0]).mean("time"))
    res = xr.concat(out, dim=xr.IndexVariable("year", np.arange(YEAR_START, YEAR_END + 1)))
    res.attrs = dict(u.attrs)
    res.attrs["season"] = label
    res.attrs["months"] = "-".join(str(m) for m in months)
    return res


def main() -> int:
    banner("03_seasonal_wind.py | 925 hPa 风场 JFMAM / JJAS 季节平均 + 异常")

    if not IN_NC.is_file():
        raise FileNotFoundError(f"找不到 {IN_NC}，先跑 scripts/01_load_ncep.py")

    with xr.open_dataset(IN_NC) as ds:
        u, v = ds["u"].load(), ds["v"].load()
    print(f"[输入] {IN_NC}")
    print(f"[输入] u 形状 {tuple(u.shape)}，时间 {str(u.time.values[0])[:7]} → "
          f"{str(u.time.values[-1])[:7]}")

    years = np.asarray(u.time.dt.year.values)
    months = np.asarray(u.time.dt.month.values)
    if u.sizes["time"] != 372:
        raise ValueError(f"输入月数 {u.sizes['time']} != 372，01 的产物不对")
    if not np.array_equal(u.time.values, v.time.values):
        raise ValueError("u 与 v 时间轴不一致")
    print(f"[输入] 覆盖年份 {years.min()}–{years.max()}，共 {np.unique(years).size} 年")

    # ---- 季节平均 ----
    u_win = season_mean(u, WINTER_MONTHS, "JFMAM")
    v_win = season_mean(v, WINTER_MONTHS, "JFMAM")
    u_sum = season_mean(u, SUMMER_MONTHS, "JJAS")
    v_sum = season_mean(v, SUMMER_MONTHS, "JJAS")
    for name, da in (("u_win", u_win), ("v_win", v_win), ("u_sum", u_sum), ("v_sum", v_sum)):
        print(f"[季节] {name} 形状 {tuple(da.shape)}，缺测 {int(np.isnan(da.values).sum())}")

    # ---- 异常场：减 31 年季节气候态（逐格点）----
    ua_win = (u_win - u_win.mean("year")).assign_attrs({"long_name": "u anomaly, JFMAM"})
    va_win = (v_win - v_win.mean("year")).assign_attrs({"long_name": "v anomaly, JFMAM"})
    ua_sum = (u_sum - u_sum.mean("year")).assign_attrs({"long_name": "u anomaly, JJAS"})
    va_sum = (v_sum - v_sum.mean("year")).assign_attrs({"long_name": "v anomaly, JJAS"})
    for name, da in (("ua_win", ua_win), ("va_win", va_win), ("ua_sum", ua_sum), ("va_sum", va_sum)):
        # 异常的 31 年平均应当为 0（浮点意义下）
        resid = float(np.abs(da.mean("year").values).max())
        print(f"[异常] {name} 时间均值最大值 {resid:.2e}（应为 0）")
        if resid > 1e-4:
            raise ValueError(f"{name} 的 31 年平均没被完全去掉（{resid}）")

    # ---- 物理量级自检（只打印，不硬断言，避免被局地地形卡住）----
    lat = np.asarray(u.lat.values)
    def zonal_u(da, lat_n):
        i = int(np.argmin(np.abs(lat - lat_n)))
        return float(np.nanmean(da.isel(lat=i).values))

    print("\n[量级] 纬向平均 u（m/s），用于判断季节循环是否合理：")
    for lat_n in (60.0, 70.0, 80.0):
        print(f"  {lat_n:4.0f}°N  JFMAM {zonal_u(u_win, lat_n):+6.2f}   "
              f"JJAS {zonal_u(u_sum, lat_n):+6.2f}")
    if zonal_u(u_win, 60.0) < zonal_u(u_sum, 60.0):
        print("  [警告] 60°N 冬季西风弱于夏季，与气候态相反，值得查一下"
              "（不中止：可能是 925 hPa 局地地形影响）")

    # ---- 写产物 ----
    ds_out = xr.Dataset(
        {
            "u_win": u_win, "v_win": v_win,
            "u_sum": u_sum, "v_sum": v_sum,
            "ua_win": ua_win, "va_win": va_win,
            "ua_sum": ua_sum, "va_sum": va_sum,
        },
        attrs={
            "title": "NCEP/NCAR R1 925 hPa seasonal mean winds and anomalies, 1979-2009",
            "source": str(IN_NC),
            "winter": "JFMAM (Jan-May of the same year, no cross-year)",
            "summer": "JJAS (Jun-Sep of the same year, no cross-year)",
            "anomaly": "seasonal mean minus the 1979-2009 seasonal climatology (per grid cell)",
            "level_hpa": "925",
            "units": "m/s",
            "n_years": str(YEAR_END - YEAR_START + 1),
            "note": "step 3 of the Ogi et al. (2010) reproduction; not detrended",
        },
    )
    ds_out["year"].attrs.update({"long_name": "year", "units": "1"})
    OUT_NC.parent.mkdir(parents=True, exist_ok=True)
    ds_out.to_netcdf(OUT_NC, mode="w")
    print(f"\n[输出] 写出 {OUT_NC}（{OUT_NC.stat().st_size / 1e6:.1f} MB）")

    # ---- 回读校验 ----
    with xr.open_dataset(OUT_NC) as chk:
        if chk.sizes["year"] != YEAR_END - YEAR_START + 1:
            raise AssertionError("回读 year 长度不对")
        for name in ("ua_win", "va_sum"):
            if not np.allclose(chk[name].values, ds_out[name].values, equal_nan=True):
                raise AssertionError(f"回读 {name} 与写入不一致")
    print("[回读] 一致")

    banner("自检汇总")
    print(f"年份            : {YEAR_START}–{YEAR_END}，{YEAR_END - YEAR_START + 1} 个")
    print(f"冬 JFMAM        : {len(WINTER_MONTHS)} 个月/年，形状 {tuple(u_win.shape)}")
    print(f"夏 JJAS         : {len(SUMMER_MONTHS)} 个月/年，形状 {tuple(u_sum.shape)}")
    print("异常            : 逐格点减去 31 年同季气候态（时间均值≈0，已断言）")
    print(f"产物            : {OUT_NC}")
    print("\n[完成] 03 正常结束。下一步：04_reg_corr.py（风场对 9 月 SIE 的回归图与相关图）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
