#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_reg_corr.py —— 925 hPa 风场对 9 月 SIE 的回归图与相关图

复现 Ogi et al. (2010) 的核心一步：把冬（JFMAM）、夏（JJAS）风异常场**对 9 月 SIE 回归**。
注意方向是「风场 regressed on SIE」，不是 SIE 对风场回归——反了系数和空间型都会变。

计算式（n = 31，df = n − 2 = 29）
    b = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²          单位 m/s per 10⁶ km²
    r = b · σ_x / σ_y                    与单位无关
    t = r · sqrt((n−2)/(1−r²))           双侧 α=0.05、df=29 的临界 |r| = 0.355

输入
    out/wind_seasonal_1979_2009.nc       03 的产物（ua/va 异常场）
    out/sie_sep.csv                      02 的产物（31 年 9 月 SIE）

输出
    out/reg_925.nc      b_u/b_v × {win,sum}，单位 m/s per 10⁶ km²
    out/corr_925.nc     r_u/r_v × {win,sum}
    figs/02_reg_maps.png                 可选；无 matplotlib 时跳过

依赖
    xarray + numpy；matplotlib 可选
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from _common import OUT, FIG, banner, read_sie, save_nc

SEASONS = {"win": "JFMAM", "sum": "JJAS"}
N_YEARS = 31
R_CRIT = 0.355          # 双侧 α=0.05, df=29 → t=2.045 → r = t/√(t²+29)
COMPONENTS = ("u", "v")


def corr_reg(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """y (n, lat, lon) 对 x (n,) 的相关与回归：返回 (r, b)，b 的单位是「每单位 x」。"""
    xc = x - x.mean()
    yc = y - y.mean(axis=0)
    cov = np.mean(xc[:, None, None] * yc, axis=0)      # 协方差（ddof 在比值中抵消）
    b = cov / np.mean(xc ** 2)
    r = b * xc.std() / yc.std(axis=0)                  # 等价于 cov/(σx·σy)
    return r, b


def load_wind() -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    with xr.open_dataset(OUT / "wind_seasonal_1979_2009.nc") as ds:
        years = np.asarray(ds["year"].values)
        lat = np.asarray(ds["lat"].values)
        lon = np.asarray(ds["lon"].values)
        fields = {f"{c}_{s}": np.asarray(ds[f"{c}a_{s}"].values)
                  for s in SEASONS for c in COMPONENTS}
    return years, lat, lon, fields


def plot(reg: dict, corr: dict, lat: np.ndarray, lon: np.ndarray) -> None:
    """极射赤面正投影（球心极坐标，手工变换，不依赖 cartopy）。绘图失败不影响 NC 产物。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"[图] matplotlib 不可用（{type(exc).__name__}），跳过作图，NC 不受影响")
        return

    try:
        lam = np.deg2rad(lon)
        rho = 90.0 - lat
        TH, RR = np.meshgrid(lam, rho)
        X, Y = RR * np.sin(TH), -RR * np.cos(TH)

        fig, axes = plt.subplots(1, 2, figsize=(11, 5.6), subplot_kw={"aspect": "equal"})
        for ax, s in zip(axes, SEASONS):
            pc = ax.pcolormesh(X, Y, corr[f"r_v_{s}"], cmap="RdBu_r", vmin=-0.8, vmax=0.8,
                               shading="gouraud")
            step = 2
            th = TH[::step, ::step]
            bu, bv = reg[f"b_u_{s}"][::step, ::step], reg[f"b_v_{s}"][::step, ::step]
            # 把 (u, v) 旋转到投影平面：east→(cosλ, sinλ)，north→(−sinλ, cosλ)
            qu = bu * np.cos(th) - bv * np.sin(th)
            qv = bu * np.sin(th) + bv * np.cos(th)
            scale = max(float(np.hypot(qu, qv).max()), 1e-9) / 4.0
            ax.quiver(X[::step, ::step], Y[::step, ::step], qu, qv,
                      color="k", scale=scale, width=0.0035, pivot="middle")
            circ = np.linspace(0, 2 * np.pi, 200)
            ax.plot(10 * np.sin(circ), -10 * np.cos(circ), color="0.75", lw=0.4)
            ax.set_axis_off()
            ax.set_title(f"{SEASONS[s]}", fontsize=11)

        cb = fig.colorbar(pc, ax=axes, shrink=0.7, pad=0.02)
        cb.set_label("correlation with Sep SIE (v-wind)", fontsize=9)
        fig.suptitle("925 hPa wind regressed on September SIE, 1979-2009\n"
                     "shading: r of v-wind; arrows: regression (m/s per $10^6$ km$^2$)",
                     fontsize=10)
        FIG.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIG / "02_reg_maps.png", dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[图] {FIG / '02_reg_maps.png'}")
    except Exception as exc:  # noqa: BLE001 - 图是附属产物，别让它拖垮统计结果
        print(f"[图] 绘图失败（{type(exc).__name__}: {exc}），NC 产物已写好，不受影响")


def main() -> int:
    banner("04_reg_corr.py | 925 hPa 风场对 9 月 SIE 的回归与相关（1979–2009）")

    years_sie, sie = read_sie()
    years, lat, lon, fields = load_wind()
    if not np.array_equal(years_sie, years):
        raise ValueError("SIE 与风场的年份不一致，先检查 02/03 的产物")
    if sie.size != N_YEARS:
        raise ValueError(f"SIE 长度 {sie.size} != {N_YEARS}")
    print(f"[输入] n = {years.size} 年（{years[0]}–{years[-1]}），SIE 均值 {sie.mean():.2f}"
          f"×10⁶ km²，网格 {lat.size}×{lon.size}")

    corr, reg = {}, {}
    for s in SEASONS:
        for c in COMPONENTS:
            corr[f"r_{c}_{s}"], reg[f"b_{c}_{s}"] = corr_reg(sie, fields[f"{c}_{s}"])
            r = corr[f"r_{c}_{s}"]
            if not np.all(np.isfinite(r)):
                raise ValueError(f"r_{c}_{s} 含 NaN")
            i = np.unravel_index(np.abs(r).argmax(), r.shape)
            n_sig = int((np.abs(r) > R_CRIT).sum())
            print(f"  {SEASONS[s]:5s} {c}-wind: max|r| = {abs(r[i]):.3f} @ "
                  f"{lat[i[0]]:+.1f}°N {lon[i[1]]:.1f}°E；|r|>{R_CRIT} 的格点 "
                  f"{n_sig}/{r.size}")

    coords = {"lat": lat, "lon": lon}
    attrs = {"source": "out/wind_seasonal_1979_2009.nc + out/sie_sep.csv",
             "method": "b = cov(w, SIE)/var(SIE); r = b*sd(SIE)/sd(w)",
             "period": f"{years[0]}-{years[-1]} (n={years.size}, df={years.size - 2})"}
    save_nc(xr.Dataset({k: (("lat", "lon"), v) for k, v in reg.items()},
                       coords=coords,
                       attrs={**attrs, "units": "m/s per 1e6 km2",
                              "note": "wind regressed ON September SIE"}),
            OUT / "reg_925.nc")
    save_nc(xr.Dataset({k: (("lat", "lon"), v) for k, v in corr.items()},
                       coords=coords,
                       attrs={**attrs, "units": "1",
                              "r_crit_0.05_df29": f"{R_CRIT}"}),
            OUT / "corr_925.nc")

    plot(reg, corr, lat, lon)

    banner("自检汇总")
    print(f"样本            : n = {years.size}，df = {years.size - 2}")
    print(f"临界相关        : |r| > {R_CRIT}（双侧 α=0.05, df=29）")
    print("回归方向        : 风场 对 SIE（不是 SIE 对风场）")
    print("产物            : out/reg_925.nc, out/corr_925.nc, figs/02_reg_maps.png")
    print("\n[完成] 04 正常结束。下一步：05_wind_index.py（异常场投影到相关图）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
