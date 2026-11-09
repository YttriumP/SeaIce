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


LAT_MIN = 55.0      # 图只画 55°N 以北（数据是全球网格，全画会把北极压成圆心一点点）
ARROW_DEG = 2.4     # 参考矢量在图上占的半径长度（度）


def _nice(v: float) -> float:
    """把数值修约到 1/1.5/2/2.5/3/4/5/6/8 ×10^k，用作参考矢量标尺。"""
    if not np.isfinite(v) or v <= 0:
        return 1.0
    e = 10.0 ** np.floor(np.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= v:
            return round(m * e, 10)
    return 10.0 * e


def _polar(lon: np.ndarray, lat: np.ndarray):
    """等距方位投影（北极中心）：rho = 90-lat，X = rho sinλ，Y = −rho cosλ。"""
    lam = np.deg2rad(lon)
    rho = 90.0 - lat
    TH, RR = np.meshgrid(lam, rho)
    return TH, RR, RR * np.sin(TH), -RR * np.cos(TH)


def plot(reg: dict, corr: dict, lat: np.ndarray, lon: np.ndarray) -> None:
    """极区地图：着色 = v 风与 SIE 的相关，箭头 = 回归矢量，点 = 通过 0.05 显著性。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"[图] matplotlib 不可用（{type(exc).__name__}），跳过作图，NC 不受影响")
        return

    try:
        north = lat >= LAT_MIN
        lat_n = lat[north]
        # 经度接缝：末尾补一列 360°，否则 0° 处会留一条白色楔形
        lon_c = np.append(lon, lon[0] + 360.0)
        TH, RR, X, Y = _polar(lon_c, lat_n)          # 闭合网格：着色与打点用
        TH0, _, X0, Y0 = _polar(lon, lat_n)          # 原始网格：矢量用（列数与数据一致）
        circ = np.linspace(0, 2 * np.pi, 361)
        step = 4                                   # 10° 一个箭头：少而清楚

        fig, axes = plt.subplots(1, 2, figsize=(9.4, 5.4), constrained_layout=True,
                                 subplot_kw={"aspect": "equal"})
        for ax, s in zip(axes, SEASONS):
            z = corr[f"r_v_{s}"][north, :]
            r_v = np.concatenate([z, z[:, :1]], axis=1)
            pc = ax.pcolormesh(X, Y, r_v, cmap="RdBu_r", vmin=-0.8, vmax=0.8,
                               shading="gouraud", rasterized=True)

            # 显著性：|r| > 0.355 处打点（抽样，避免糊成一片）
            sig = (np.abs(r_v) > R_CRIT)[::2, ::2]
            ax.scatter(X[::2, ::2][sig], Y[::2, ::2][sig], s=2.0, c="0.18",
                       marker=".", linewidths=0, alpha=0.45, rasterized=True)

            # 回归矢量：先旋转到投影平面，再按参考矢量统一缩放
            th = TH0[::step, ::step]
            bu = reg[f"b_u_{s}"][north, :][::step, ::step]
            bv = reg[f"b_v_{s}"][north, :][::step, ::step]
            qu = bu * np.cos(th) - bv * np.sin(th)
            qv = bu * np.sin(th) + bv * np.cos(th)
            ref = _nice(float(np.nanpercentile(np.hypot(qu, qv), 92)))
            q = ax.quiver(X0[::step, ::step], Y0[::step, ::step], qu, qv,
                          scale=ref / ARROW_DEG, scale_units="xy", angles="xy",
                          color="0.08", width=0.0022, headwidth=3.6, headlength=4.6,
                          headaxislength=4.0, pivot="middle")
            # 参考矢量放在左下角（55°N 圆外的空白区），避免被 tight bbox 裁掉
            ax.quiverkey(q, 0.055, 0.055, ref, f"{ref:g} m/s per $10^6$ km$^2$",
                         coordinates="axes", labelpos="E", labelsep=0.04,
                         fontproperties={"size": 6.5}, labelcolor="0.3")

            # 经纬网 + 纬度标签（放右侧圈外，避免压住数据）
            for r_, lab in ((35, "55°N"), (30, "60°N"), (20, "70°N"), (10, "80°N")):
                ax.plot(r_ * np.sin(circ), -r_ * np.cos(circ),
                        color="0.72", lw=0.35, zorder=3)
                ax.text(r_ + 0.9, 0.0, lab, fontsize=5.5, color="0.35",
                        ha="left", va="center", zorder=6,
                        bbox={"boxstyle": "round,pad=0.12", "fc": "white",
                              "ec": "none", "alpha": 0.8})
            for ang in range(0, 360, 45):
                a = np.deg2rad(ang)
                ax.plot([0, 35 * np.sin(a)], [0, -35 * np.cos(a)],
                        color="0.88", lw=0.3, zorder=0)

            ax.set_xlim(-37, 39)
            ax.set_ylim(-37, 37)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.set_title(SEASONS[s], fontsize=10, pad=2)

        cb = fig.colorbar(pc, ax=axes, shrink=0.62, pad=0.02, extend="both")
        cb.set_label("correlation between v-wind and Sep SIE", fontsize=7.5)
        cb.ax.tick_params(labelsize=7)
        fig.suptitle("925 hPa wind regressed on September SIE, 1979-2009   "
                     "(shading: r of v-wind; dots: |r| > 0.355, p < 0.05)",
                     fontsize=8.5)
        FIG.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIG / "02_reg_maps.png", dpi=300, bbox_inches="tight",
                    facecolor="white")
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
