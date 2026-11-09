#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_reg_corr.py —— 925 hPa 风场对 9 月 SIE 的回归图与相关图

复现 Ogi et al. (2010) 的核心一步：把冬（JFMAM）、夏（JJAS）风异常场**对 9 月 SIE 回归**。
方向是「风场 regressed on SIE」，反了系数与空间型都会变。

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
    figs/02_reg_maps.png                 极区矢量图（灰陆地、白海洋、60°N 边界）

出图两条路
    1) cartopy（优先）：投影旋转与陆地都由 cartopy 处理，效果最接近原文；
       但 cfeature.LAND 首次运行要下载 Natural Earth 数据，无外网会失败。
    2) 离线回退：读同目录 _coastline.npz（Natural Earth 110m，36 KB，随仓库分发），
       自己算极坐标投影并裁剪到 60°N —— 不联网、不依赖 cartopy。

依赖
    xarray + numpy；matplotlib；cartopy（可选）
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from _common import OUT, FIG, banner, read_sie, save_nc

SEASONS = {"win": "JFMAM", "sum": "JJAS"}
N_YEARS = 31
R_CRIT = 0.355          # 双侧 α=0.05, df=29 → t=2.045 → r = t/√(t²+29)
COMPONENTS = ("u", "v")

LAT_MIN = 60.0          # 视场：60°N 以北，与原文一致
LAT_ARROW_MAX = 84.0    # 更北不画箭头：经线在极点挤成一圈黑环
ARROW_DEG = 2.6         # 参考矢量的半径长度（度）
ARROW_CLIP = 2.2        # 超过参考值 2.2 倍的箭头截断，避免个别极值撑爆版面
COAST_NPZ = Path(__file__).with_name("_coastline.npz")


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 出图工具
# ---------------------------------------------------------------------------
def _nice(v: float) -> float:
    """把数值修约到 1/1.5/2/2.5/3/4/5/6/8 ×10^k，用作参考矢量标尺。"""
    if not np.isfinite(v) or v <= 0:
        return 1.0
    e = 10.0 ** np.floor(np.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= v:
            return round(m * e, 10)
    return 10.0 * e


def _arrow_ref(u: np.ndarray, v: np.ndarray) -> float:
    """参考矢量取 75 百分位：多数箭头接近满长，少数极值靠 ARROW_CLIP 截断。"""
    return _nice(float(np.nanpercentile(np.hypot(u, v), 75)))


def _samples(lat_n: np.ndarray, lon: np.ndarray, u: np.ndarray, v: np.ndarray):
    """
    按纬度自适应稀疏化：经线在极点收敛，固定经度间隔会让箭头挤成一圈。
    同时丢掉 84°N 以北，那里只剩噪声。
    """
    la, lo, uu, vv = [], [], [], []
    for j, phi in enumerate(lat_n):
        if phi > LAT_ARROW_MAX:
            continue
        s = max(2, int(round(1.0 / max(np.cos(np.deg2rad(phi)), 0.06))))
        la.append(np.full(lon[::s].size, phi))
        lo.append(lon[::s])
        uu.append(u[j, ::s])
        vv.append(v[j, ::s])
    return (np.concatenate(la), np.concatenate(lo),
            np.concatenate(uu), np.concatenate(vv))


def _clip_mag(u: np.ndarray, v: np.ndarray, ref: float) -> tuple[np.ndarray, np.ndarray]:
    """把超过 ARROW_CLIP×ref 的矢量截断到该长度，方向不变。"""
    mag = np.hypot(u, v)
    limit = ARROW_CLIP * ref
    f = np.where(mag > limit, limit / np.maximum(mag, 1e-12), 1.0)
    return u * f, v * f


def _plot_cartopy(reg: dict, corr: dict, lat: np.ndarray, lon: np.ndarray, plt) -> bool:
    """优先路径：cartopy 处理投影/陆地/海岸线；数据缺失等任何异常都返回 False。"""
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except Exception as exc:  # noqa: BLE001
        print(f"[图] cartopy 不可用（{type(exc).__name__}），改用离线海岸线")
        return False

    try:
        import matplotlib.path as mpath
        proj = ccrs.NorthPolarStereo(central_longitude=0)
        north = lat >= LAT_MIN
        lat_n = lat[north]
        LONg, LATg = np.meshgrid(lon, lat_n)
        circ = np.arange(0.0, 361.0, 1.0)
        # 把坐标轴裁成圆形，否则 60°N 圆会被矩形边框切掉四个角
        theta = np.linspace(0.0, 2 * np.pi, 181)
        circle = mpath.Path(np.column_stack([np.sin(theta), np.cos(theta)]) * 0.5 + 0.5)

        fig = plt.figure(figsize=(10.0, 5.4), constrained_layout=True)
        for i, (s, tag) in enumerate(zip(SEASONS, ("(a)", "(b)"))):
            ax = fig.add_subplot(1, 2, i + 1, projection=proj)
            ax.set_extent([-180, 180, LAT_MIN, 90], crs=ccrs.PlateCarree())
            ax.set_boundary(circle, transform=ax.transAxes)
            ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#d9d9d9",
                           edgecolor="0.35", linewidth=0.35, zorder=6)
            ax.coastlines(resolution="110m", linewidth=0.35, color="0.35", zorder=7)
            ax.gridlines(xlocs=range(-180, 180, 30), ylocs=[70, 80],
                         linestyle=":", linewidth=0.4, color="0.65", zorder=1)
            ax.plot(circ, np.full(circ.size, LAT_MIN), transform=ccrs.PlateCarree(),
                    color="0.4", lw=0.6, zorder=8)

            z = corr[f"r_v_{s}"][north, :]
            sig = np.abs(z) > R_CRIT
            ax.scatter(LONg[sig], LATg[sig], s=1.6, c="0.35", marker=".", linewidths=0,
                       alpha=0.35, transform=ccrs.PlateCarree(), zorder=2)

            la_s, lo_s, bu, bv = _samples(lat_n, lon, reg[f"b_u_{s}"][north, :],
                                          reg[f"b_v_{s}"][north, :])
            ref = _arrow_ref(bu, bv)
            bu, bv = _clip_mag(bu, bv, ref)
            q = ax.quiver(lo_s, la_s, bu, bv, transform=ccrs.PlateCarree(),
                          scale=ref / 0.12, scale_units="inches", color="0.05",
                          width=0.0014, headwidth=3.2, headlength=4.0,
                          headaxislength=3.6, pivot="middle", zorder=3)
            # 圆内左下角，避开陆地主体；标尺要压在陆地之上
            k = ax.quiverkey(q, 0.30, 0.075, ref, f"{ref:g} m/s per $10^6$ km$^2$",
                             coordinates="axes", labelpos="E", labelsep=0.04,
                             fontproperties={"size": 6}, labelcolor="0.2")
            k.set_zorder(20)
            for lat_lab in (70, 80):
                ax.text(180, lat_lab, f"{lat_lab}°N", transform=ccrs.PlateCarree(),
                        fontsize=5, color="0.35", ha="right", va="center", zorder=9)
            ax.set_title(f"{tag} {SEASONS[s]}", fontsize=9, pad=0)

        fig.text(0.5, 0.005,
                 "925 hPa wind anomaly regressed on September SIE (arrows, m/s per "
                 "$10^6$ km$^2$); dots: |r| > 0.355 (p < 0.05)",
                 ha="center", fontsize=6.5, color="0.3")
        _save(fig, plt)
        return True
    except Exception as exc:  # noqa: BLE001 - 多为 Natural Earth 数据下载失败
        print(f"[图] cartopy 路径失败（{type(exc).__name__}: {str(exc)[:80]}），改用离线海岸线")
        plt.close("all")
        return False


def _plot_local(reg: dict, corr: dict, lat: np.ndarray, lon: np.ndarray, plt) -> None:
    """回退路径：自己算极坐标投影 + 打包的陆地多边形，不联网。"""
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Circle, Polygon

    north = lat >= LAT_MIN
    lat_n = lat[north]
    lam = np.deg2rad(lon)
    rho = 90.0 - lat_n
    TH0, RR = np.meshgrid(lam, rho)
    X0, Y0 = RR * np.sin(TH0), -RR * np.cos(TH0)
    r_out = 90.0 - LAT_MIN
    ang = np.deg2rad(np.arange(0.0, 360.0, 2.0))

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 5.4), constrained_layout=True,
                             subplot_kw={"aspect": "equal"})
    for ax, s, tag in zip(axes, SEASONS, ("(a)", "(b)")):
        clip = Circle((0, 0), r_out, transform=ax.transData,
                      facecolor="white", edgecolor="none", zorder=0)
        ax.add_patch(clip)

        if COAST_NPZ.is_file():
            d = np.load(COAST_NPZ)
            clon, clat, starts = d["lon"].astype(float), d["lat"].astype(float), d["starts"]
            polys = []
            for k, i0 in enumerate(starts):
                i1 = starts[k + 1] if k + 1 < starts.size else clon.size
                seg_lat = clat[i0:i1]
                # 只要北半球的环：南极洲那种绕极一圈的多边形会把整个盘面填满
                if seg_lat.size < 3 or seg_lat.max() < 40.0:
                    continue
                seg = np.unwrap(np.deg2rad(clon[i0:i1]))
                r_ = 90.0 - seg_lat
                polys.append(Polygon(np.column_stack([r_ * np.sin(seg),
                                                      -r_ * np.cos(seg)]), closed=True))
            coll = PatchCollection(polys, facecolor="#d9d9d9", edgecolor="0.35",
                                   linewidths=0.35, zorder=6)
            coll.set_clip_path(clip)
            ax.add_collection(coll)

        ax.plot(r_out * np.sin(ang), -r_out * np.cos(ang), color="0.4", lw=0.5, zorder=8)
        for a in ang[::2]:
            ax.plot([r_out * np.sin(a), (r_out + 0.7) * np.sin(a)],
                    [-r_out * np.cos(a), -(r_out + 0.7) * np.cos(a)],
                    color="0.4", lw=0.3, zorder=8, clip_on=False)
        for r_ in (10.0, 20.0):
            ax.plot(r_ * np.sin(ang), -r_ * np.cos(ang), ls=":", color="0.65",
                    lw=0.4, zorder=1)

        z = corr[f"r_v_{s}"][north, :]
        sig = np.abs(z) > R_CRIT
        ax.scatter(X0[sig], Y0[sig], s=1.6, c="0.35", marker=".", linewidths=0,
                   alpha=0.35, rasterized=True, zorder=2)

        la_s, lo_s, bu, bv = _samples(lat_n, lon, reg[f"b_u_{s}"][north, :],
                                      reg[f"b_v_{s}"][north, :])
        ref = _arrow_ref(bu, bv)
        bu, bv = _clip_mag(bu, bv, ref)
        # 极射赤面投影下把 (u, v) 旋转到图面：east→(cosλ, sinλ)，north→(−sinλ, cosλ)
        lam_s = np.deg2rad(lo_s)
        rho_s = 90.0 - la_s
        xs, ys = rho_s * np.sin(lam_s), -rho_s * np.cos(lam_s)
        qu = bu * np.cos(lam_s) - bv * np.sin(lam_s)
        qv = bu * np.sin(lam_s) + bv * np.cos(lam_s)
        q = ax.quiver(xs, ys, qu, qv,
                      scale=ref / ARROW_DEG, scale_units="xy", angles="xy",
                      color="0.05", width=0.0014, headwidth=3.2, headlength=4.0,
                      headaxislength=3.6, pivot="middle", zorder=3)
        k = ax.quiverkey(q, 0.035, 0.03, ref, f"{ref:g} m/s per $10^6$ km$^2$",
                         coordinates="axes", labelpos="E", labelsep=0.05,
                         fontproperties={"size": 6}, labelcolor="0.25")
        k.set_zorder(20)
        for r_, lab in ((20.0, "70°N"), (10.0, "80°N")):
            ax.text(0.68 * r_ + 0.4, -0.68 * r_ - 0.4, lab, fontsize=5, color="0.35",
                    ha="left", va="top", zorder=9,
                    bbox={"boxstyle": "round,pad=0.1", "fc": "white", "ec": "none",
                          "alpha": 0.7})

        ax.set_xlim(-32.6, 32.6)
        ax.set_ylim(-32.6, 32.6)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"{tag} {SEASONS[s]}", fontsize=9, pad=0)

    fig.text(0.5, 0.015,
             "925 hPa wind anomaly regressed on September SIE (arrows, m/s per "
             "$10^6$ km$^2$); dots: |r| > 0.355 (p < 0.05)",
             ha="center", fontsize=6.5, color="0.3")
    _save(fig, plt)


def _save(fig, plt) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "02_reg_maps.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[图] {FIG / '02_reg_maps.png'}")


def plot(reg: dict, corr: dict, lat: np.ndarray, lon: np.ndarray) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"[图] matplotlib 不可用（{type(exc).__name__}），跳过作图，NC 不受影响")
        return
    if not _plot_cartopy(reg, corr, lat, lon, plt):
        _plot_local(reg, corr, lat, lon, plt)


# ---------------------------------------------------------------------------
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
                       attrs={**attrs, "units": "1", "r_crit_0.05_df29": f"{R_CRIT}"}),
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
