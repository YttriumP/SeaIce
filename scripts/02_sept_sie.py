#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_sept_sie.py —— 从 Bootstrap SIC 算北极 9 月 SIE 年序列（31 年）与 ΔSIE（30 年）

目的
    复现 Ogi et al. (2010) 的预报对象：1979–2009 年北极 9 月海冰范围（SIE）年序列，
    并给出年际差分 ΔSIE = SIE(当年) − SIE(上一年)。这是后面回归、投影、R² 的因变量。

输入（只读，禁止写入/删除/移动）
    /SSD1/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc
        变量 ice(time, lat, lon)，double，_FillValue = -999（陆地与缺测）
        网格 1°×1°（lat 180、lon 360），由 25 km 极射赤面网格双线性重采样而来
        时间 530 个月，time:units = "months since 1970-01-01"，首月 1978-11、末月 2022-12

输出
    out/sie_sep.csv    31 行：year, sie_1e6km2（单位 10^6 km²）
    out/dsie.csv       30 行：year, dsie     （year = 1980…2009）
    figs/01_sie_series.png   可选；matplotlib 缺失时自动跳过（不影响 CSV）

依赖
    xarray + numpy；matplotlib 可选（若用，强制 Agg 后端）

口径（glossary.md §2 / §5，**不要改**）
    - 产品：Bootstrap SIC（NSIDC-0051），**不是** Sea Ice Index
    - 变量：extent —— 格点浓度 > 15% 即整格记为 100%，按格点面积求和（不是面积加权平均）
    - 阈值：严格 `sic > 15`（等于 15% 的格点不计；Bootstrap 是 0.1% 步长，边界值几乎不出现）
    - 区域：北半球（lat > 0）；本文件是全球网格，**必须**去掉南半球，否则会把南极冰算进来
    - 时段：1979–2009 含首尾，共 31 个 9 月
    - 面积：球面梯形公式 A = R² · |Δλ| · |sinφ₂ − sinφ₁|，φ 取格点中心 ±Δφ/2（裁剪到 ±90°）
            R = 6371.0 km（IUGG 平均半径）。换用赤道半径 6378.137 km 会使 SIE 整体 ×1.0022，
            对年际变化与相关分析的结论无影响，但绝对值会差 0.2%。

已知局限（写结论时必须带上）
    本文件是**双线性重采样**到 1° 的（属性 ice:remap 已写明）。重采样会平滑冰边缘，
    使 15% 阈值的判定与原 25 km 网格不同，SIE 绝对值会有几个百分点的差异。
    与 `sic_psn25_..._v05r00.nc` 的对比属于 decisions.md 的 Q3，另算。
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

try:
    import numpy as np
    import xarray as xr
except ImportError as exc:  # pragma: no cover
    sys.exit(
        f"缺少依赖: {exc.name}\n"
        "本项目服务器上 /usr/bin/python3 已含 xarray + netcdf4，"
        "若确实缺失再建虚拟环境：python3 -m venv .venv && .venv/bin/pip install -U xarray netcdf4"
    )

# ---------------------------------------------------------------------------
# 口径常量（改这里 = 改口径 = 作废）
# ---------------------------------------------------------------------------
YEAR_START, YEAR_END = 1979, 2009
N_YEARS = YEAR_END - YEAR_START + 1          # 31
N_DELTA = N_YEARS - 1                        # 30

THRESHOLD_PCT = 15.0                         # extent 阈值（%），严格 >
EARTH_RADIUS_KM = 6371.0                     # IUGG 平均半径
EQUATORIAL_RADIUS_KM = 6378.137              # 仅用于打印半径选择的敏感性

FILL = -999.0
HUGE = 1.0e30

# 数据只读；优先 SSD
SIC_CANDIDATES = [
    Path("/SSD1/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc"),
    Path("/data/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc"),
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "out"
FIG_DIR = PROJECT_ROOT / "figs"
OUT_SIE = OUT_DIR / "sie_sep.csv"
OUT_DSIE = OUT_DIR / "dsie.csv"
OUT_FIG = FIG_DIR / "01_sie_series.png"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def resolve_sic_path() -> Path:
    for p in SIC_CANDIDATES:
        if p.is_file():
            print(f"[路径] SIC 文件 = {p}")
            return p
    tried = "\n  ".join(str(p) for p in SIC_CANDIDATES)
    raise FileNotFoundError(
        f"找不到 Bootstrap SIC 文件，已尝试:\n  {tried}\n"
        "（数据盘只读，请确认挂载；不要用别的海冰产品替代）"
    )


def decode_month_index(raw: np.ndarray, units: str) -> tuple[np.ndarray, np.ndarray]:
    """
    把原始时间数值换算成 (year, month)。

    本文件的 units 是 "months since 1970-01-01" —— CF 里 "months since" 属于
    非固定长度单位，不同 xarray/cftime 版本处理不一致，所以这里**不用**自动解码，
    直接按月序号做整数运算，对逐月数据是精确的。
    """
    m = re.match(r"\s*(\w+)\s+since\s+(\d{4})-(\d{1,2})-(\d{1,2})", units)
    if not m:
        raise ValueError(f"无法解析 time:units = {units!r}")
    step, y0, m0, d0 = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    raw = np.asarray(raw, dtype="float64")

    if step == "months":
        if np.any(np.abs(raw - np.round(raw)) > 1e-9):
            raise ValueError("time 不是整数月，不能按月序号解码")
        ym = y0 * 12 + (m0 - 1) + raw.astype("int64")
    elif step in {"days", "hours"}:
        # 兜底：换算成 datetime64 再取年月（本文件走不到这条）
        factor = 86400 if step == "days" else 3600
        t0 = np.datetime64(f"{y0:04d}-{m0:02d}-{d0:02d}", "s")
        t = t0 + (raw * factor).astype("timedelta64[s]")
        years = t.astype("datetime64[Y]").astype(int) + 1970
        months = t.astype("datetime64[M]").astype(int) % 12 + 1
        return years, months
    else:
        raise ValueError(f"不支持的时间步长 {step!r}（只处理 months/days/hours）")

    return (ym // 12).astype("int64"), (ym % 12 + 1).astype("int64")


def cell_area_km2(lat: np.ndarray, lon: np.ndarray, radius_km: float) -> np.ndarray:
    """
    规则经纬网格的球面梯形面积，返回 (lat, lon) 二维数组，单位 km²。

        A = R² · |Δλ| · |sin φ_hi − sin φ_lo|

    φ_hi/φ_lo 取格点中心 ±Δφ/2，并裁剪到 ±90°，这样极点附近的半个格子也算对。
    """
    lat = np.asarray(lat, dtype="float64")
    lon = np.asarray(lon, dtype="float64")
    if lat.size < 2 or lon.size < 2:
        raise ValueError("lat/lon 至少各需 2 个格点")

    dlat = np.abs(np.diff(lat))
    dlon = np.abs(np.diff(lon))
    if np.ptp(dlat) > 1e-6 or np.ptp(dlon) > 1e-6:
        raise ValueError(
            f"网格不等间距（Δlat 范围 {dlat.min():.4f}–{dlat.max():.4f}，"
            f"Δlon 范围 {dlon.min():.4f}–{dlon.max():.4f}），梯形公式不适用"
        )
    dlat, dlon = float(dlat.mean()), float(dlon.mean())

    lat_hi = np.clip(lat + dlat / 2.0, -90.0, 90.0)
    lat_lo = np.clip(lat - dlat / 2.0, -90.0, 90.0)
    dsin = np.abs(np.sin(np.deg2rad(lat_hi)) - np.sin(np.deg2rad(lat_lo)))

    area_by_lat = radius_km ** 2 * np.deg2rad(dlon) * dsin   # (lat,)
    return np.repeat(area_by_lat[:, None], lon.size, axis=1)  # (lat, lon)


def write_csv(path: Path, header: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    print(f"[输出] 写出 {path}（{len(rows)} 行数据 + 1 行表头）")


def make_figure(years: np.ndarray, sie: np.ndarray) -> None:
    """可选的图：matplotlib 不可用时跳过，不影响 CSV 产物。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"[图] matplotlib 不可用（{type(exc).__name__}），跳过作图，CSV 不受影响")
        return

    slope, intercept = np.polyfit(years.astype(float), sie, 1)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.plot(years, sie, "o-", color="#1f4e79", lw=1.4, ms=3.5, label="September SIE")
    ax.plot(years, slope * years + intercept, "--", color="#c00000", lw=1.0,
            label=f"linear trend {slope * 10:+.2f} per decade")
    imin = int(np.argmin(sie))
    ax.annotate(f"{int(years[imin])}", xy=(years[imin], sie[imin]),
                xytext=(6, 6), textcoords="offset points", fontsize=8, color="0.3")
    ax.set_xlabel("Year")
    ax.set_ylabel(r"SIE ($10^6$ km$^2$)")
    ax.set_title("Arctic September sea-ice extent, Bootstrap SIC, 1979-2009")
    ax.grid(alpha=0.3, lw=0.5)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=300)
    plt.close(fig)
    print(f"[图] 写出 {OUT_FIG}（300 dpi）")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    banner("02_sept_sie.py | Bootstrap SIC → 北极 9 月 SIE（31 年）+ ΔSIE（30 年）")

    path = resolve_sic_path()
    # decode_times=False：时间按月序号自己算，避开 "months since" 的版本差异；
    # _FillValue/missing_value 仍然由 xarray 解成 NaN
    ds = xr.open_dataset(path, decode_times=False)
    try:
        if "ice" not in ds:
            raise KeyError(f"文件里没有变量 ice，实际变量: {list(ds.data_vars)}")

        ice = ds["ice"]
        lat = np.asarray(ds["lat"].values, dtype="float64")
        lon = np.asarray(ds["lon"].values, dtype="float64")
        raw_t = np.asarray(ds["time"].values)

        print(f"[数据] 变量 ice 形状 = {tuple(ice.shape)}，dims = {tuple(ice.dims)}，"
              f"dtype = {ice.dtype}")
        print(f"[数据] lat = {lat.min():g} … {lat.max():g}（{lat.size} 格），"
              f"lon = {lon.min():g} … {lon.max():g}（{lon.size} 格）")
        print(f"[数据] time:units = {ds['time'].attrs.get('units')!r}，"
              f"原始值范围 = {raw_t.min()} … {raw_t.max()}")

        years, months = decode_month_index(raw_t, str(ds["time"].attrs.get("units", "")))
        print(f"[时间] 解码后 = {years[0]}-{months[0]:02d} … {years[-1]}-{months[-1]:02d}，"
              f"共 {years.size} 个月")
        if not np.all(np.diff(years * 12 + months) == 1):
            raise ValueError("时间轴不是逐月连续，检查 time 变量")
        if years.size != 530:
            print(f"[警告] 文件月数 {years.size}，与文件名 197811-202212（530 个月）不符")

        # ---- 浓度单位自检：这个文件没有 units 属性，只能看量级 ----
        vals = np.asarray(ice.values)
        finite = vals[np.isfinite(vals) & (np.abs(vals) < HUGE)]
        vmax = float(finite.max()) if finite.size else float("nan")
        if vmax > 1.5:
            scale, unit = 1.0, "%"
        elif vmax <= 1.0:
            scale, unit = 100.0, "fraction"
            print(f"[单位] 最大值 {vmax:.3f} ≤ 1，判定为 0–1，已 ×100 转成 %")
        else:
            raise ValueError(f"浓度最大值 {vmax:.3f} 落在 1–1.5 之间，无法判定单位，停下")
        print(f"[单位] 浓度按 {unit} 处理（有限值最大 {vmax:.2f}）")
        ice = ice * scale

        # ---- 缺测统计 ----
        n_nan_all = int(np.isnan(vals).sum())
        n_fill_attr = float(ice.attrs.get("_FillValue", FILL))
        print(f"[缺测] 全文件 NaN = {n_nan_all} 个（{n_nan_all / vals.size * 100:.2f}%），"
              f"_FillValue = {n_fill_attr:g}（xarray 已解成 NaN）")
        n_huge = int((np.abs(vals) > HUGE).sum())
        if n_huge:
            print(f"[缺测] 发现 {n_huge} 个未解码的大数，已置为 NaN")
            ice = ice.where(np.abs(ice) < HUGE)
        # 兜底：万一 xarray 没把 -999 解成 NaN（不同版本的 _FillValue/missing_value 处理差异）
        n_fill_lit = int((vals == FILL).sum())
        if n_fill_lit:
            print(f"[缺测] 发现 {n_fill_lit} 个字面 -999 未被解码，已置为 NaN")
            ice = ice.where(ice != FILL)

        # ---- 格点面积 ----
        area = cell_area_km2(lat, lon, EARTH_RADIUS_KM)          # (lat, lon) km²
        north = lat > 0.0                                        # 只要北半球
        area_nh = float(area[north, :].sum())
        print(f"[面积] 格点面积 {area.min():.1f}–{area.max():.1f} km²，"
              f"北半球总面积 {area_nh / 1e6:.1f}×10⁶ km²（理论 2πR² = 254.9×10⁶）")
        if not (240e6 < area_nh < 270e6):
            raise ValueError(f"北半球总面积 {area_nh:.3e} km² 不合理，面积公式或网格有问题")
        print(f"[面积] 半径取 {EARTH_RADIUS_KM:g} km；若取赤道半径 {EQUATORIAL_RADIUS_KM:g} km，"
              f"SIE 整体 ×{(EQUATORIAL_RADIUS_KM / EARTH_RADIUS_KM) ** 2:.4f}")

        # 南半球 9 月有大量海冰：证明必须加 north 遮罩，而不是靠"北极网格本来就没有南半球"
        sample = ice.isel(time=0).values
        sh = lat <= 0.0
        n_sh_ice = int((sample[sh, :] > THRESHOLD_PCT).sum())
        print(f"[区域] 首个时次南半球 >15% 的格点 = {n_sh_ice} 个 → "
              f"{'确是全球网格，已加北半球遮罩' if n_sh_ice > 0 else '南半球本来就无冰'}")

        # ---- 选 1979–2009 的 9 月 ----
        sel = (years >= YEAR_START) & (years <= YEAR_END) & (months == 9)
        idx = np.where(sel)[0]
        print(f"[切片] 1979–2009 的 9 月共 {idx.size} 个（期望 {N_YEARS}）")
        if idx.size == 0:
            raise ValueError("一个 9 月都没选中，检查时间解码")
        if idx.size != N_YEARS:
            raise ValueError(f"9 月个数 {idx.size} != {N_YEARS}，时段口径不对")

        ice_sep = ice.isel(time=idx)
        yrs = years[idx]
        print(f"[切片] 首/末：{yrs[0]}-09 / {yrs[-1]}-09；切片形状 {tuple(ice_sep.shape)}")

        # 9 月切片内的缺测（与全文件分开统计，这才影响结果）
        sep_vals = ice_sep.values
        n_nan_sep = int(np.isnan(sep_vals).sum())
        print(f"[缺测] 31 个 9 月切片内 NaN = {n_nan_sep} 个"
              f"（占 {n_nan_sep / sep_vals.size * 100:.1f}%，含南极与陆地）")

        # ---- extent：> 15% 记满格，按面积求和 ----
        # NaN > 15 结果为 False，天然不计入；北半球遮罩把南极挡掉
        mask = (ice_sep > THRESHOLD_PCT).values & north[None, :, None]
        area2d = area[None, :, :]
        sie_km2 = (mask * area2d).sum(axis=(1, 2))
        sie = sie_km2 / 1e6                                      # 10^6 km²

        n_cells = mask.sum(axis=(1, 2))
        print(f"[extent] 每年达标格点数 {n_cells.min()}–{n_cells.max()}"
              f"（1° 网格上，75°N 附近单格约 3.2 千 km²，6–7×10⁶ km² 对应约 2 千格）")

        # ---- 硬性检查 ----
        if not np.all(np.isfinite(sie)):
            raise ValueError("SIE 序列里有非有限值")
        if not np.all((3.0 <= sie) & (sie <= 9.0)):
            raise ValueError(f"SIE 超出合理范围 3–9×10⁶ km²：{sie}")
        assert len(sie) == N_YEARS, f"len(sie) = {len(sie)} != {N_YEARS}"

        dsie = np.diff(sie)                                      # 长度 30
        dsie_years = yrs[1:]
        assert len(dsie) == N_DELTA, f"len(dsie) = {len(dsie)} != {N_DELTA}"
        if not np.all(np.isfinite(dsie)):
            raise ValueError("ΔSIE 里有非有限值（1980–2009 不应有缺测）")

        # ---- 写 CSV ----
        write_csv(
            OUT_SIE, ["year", "sie_1e6km2"],
            [(int(y), f"{v:.6f}") for y, v in zip(yrs, sie)],
        )
        write_csv(
            OUT_DSIE, ["year", "dsie"],
            [(int(y), f"{v:.6f}") for y, v in zip(dsie_years, dsie)],
        )

        # ---- 回读校验（防止写出去的和算出来的不一致）----
        for p, n_exp, head in ((OUT_SIE, N_YEARS, "sie_1e6km2"), (OUT_DSIE, N_DELTA, "dsie")):
            with open(p, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            if rows[0] != ["year", head]:
                raise AssertionError(f"{p.name} 表头不对: {rows[0]}")
            if len(rows) - 1 != n_exp:
                raise AssertionError(f"{p.name} 数据行 {len(rows) - 1} != {n_exp}")
        print("[回读] 两个 CSV 的行数与表头正确")

        make_figure(yrs, sie)

        # ---- 打印年序列，便于与原文 Fig.1 目视对比 ----
        banner("北极 9 月 SIE 年序列（Bootstrap SIC, 10^6 km²）")
        for y, v in zip(yrs, sie):
            bar = "#" * int(round((v - 3.0) / 9.0 * 60))
            print(f"  {y}  {v:6.2f}  {bar}")

        slope = float(np.polyfit(yrs.astype(float), sie, 1)[0])
        imin, imax = int(np.argmin(sie)), int(np.argmax(sie))

        banner("自检汇总")
        print(f"文件            : {path}")
        print(f"原始形状        : {tuple(ice.shape)}  (time, lat, lon)")
        print(f"时间范围        : {years[0]}-{months[0]:02d} → {years[-1]}-{months[-1]:02d}"
              f"（{years.size} 个月，逐月连续）")
        print(f"选取            : 1979–2009 的 9 月，{idx.size} 个")
        print(f"缺测            : 全文件 {n_nan_all}，9 月切片 {n_nan_sep}")
        print(f"SIE 长度        : {len(sie)}（断言 == {N_YEARS}）")
        print(f"ΔSIE 长度       : {len(dsie)}（断言 == {N_DELTA}）")
        print(f"SIE 范围        : {sie.min():.2f}（{yrs[imin]}）– {sie.max():.2f}（{yrs[imax]}）×10⁶ km²")
        print(f"线性趋势        : {slope * 10:+.3f} ×10⁶ km²/decade（仅作量级参考，不是复现目标）")
        print(f"ΔSIE 范围       : {dsie.min():+.2f} … {dsie.max():+.2f} ×10⁶ km²")
        print(f"产物            : {OUT_SIE}")
        print(f"                  {OUT_DSIE}")
        print("\n[完成] 02_sept_sie.py 正常结束。下一步：03_seasonal_wind.py"
              "（JFMAM / JJAS 季节平均）")
        return 0
    finally:
        ds.close()


if __name__ == "__main__":
    sys.exit(main())
