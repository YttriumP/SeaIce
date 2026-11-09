# NCL → Python 对照表

> 用途：组里 legacy 代码是 NCL，新分析走 Python。翻译时不必从零推理，先查这张表。
> 原则：**能查到函数就照抄语义，查不到就先打印小数组和 NCL 结果比对**，不要盲信。

---

## 一、读写与基本操作

| NCL | Python | 备注 |
|---|---|---|
| `addfile("r", f)` | `xr.open_dataset(f)` | xarray 自动保留坐标与属性 |
| `addfiles(...)` + `filevar` | `xr.open_mfdataset(paths, combine="by_coords")` | 多文件按时间合并 |
| `f->var` | `ds["var"]` | 变量名大小写敏感 |
| `new(...)` / `delete(...)` | 直接赋值 / `del` | 不需要手动管理内存 |
| `(/1,2,3/)` | `[1, 2, 3]` 或 `np.array(...)` | xarray 运算优先用 `xr.DataArray` |
| `sprintf("%5.2f", x)` | `f"{x:5.2f}"` | — |
| `systemfunc("...")` | `subprocess.run(...)` | 少用，尽量用 Python API |

## 二、统计与集合运算（最容易踩坑的一类）

| NCL | Python | 备注 |
|---|---|---|
| `dim_avg_n_Wrap(x, 0)` | `x.mean(dim="time")` | **NCL 用 0-based 维序号，xarray 用维名**——翻译第一大坑 |
| `dim_sum_n` | `.sum(dim=...)` | 同上 |
| `dim_stddev_n` | `.std(dim=...)` | 默认 ddof=0，NCL 也是总体标准差 |
| `dim_standardize_n` | `(x - x.mean(dim)) / x.std(dim)` | — |
| `dim_rmvmean_n` | `x - x.mean(dim)` | — |
| `dim_max_n` / `dim_min_n` | `.max(dim)` / `.min(dim)` | — |
| `escorc(x, y)` | `xr.corr(x, y, dim="time")` | 逐格点时配合广播 |
| `regCoef_n(x, y, 0, 0)` | `xr.apply_ufunc(scipy.stats.linregress, ...)` 或 `x.polyfit("time", 1)` | **参数顺序：x 自变量、y 因变量**；返回斜率。要截距时用 `linregress` |
| `ttest(...)` | `scipy.stats.ttest_ind` / `ttest_1samp` | NCL 返回 t 值与概率，Python 分开给 |
| `trend_manken` | `pymannkendall` | 非参数趋势，别和线性趋势混用 |
| `runave_n_Wrap(x, w, 0, 0)` | `x.rolling(time=w, center=True).mean()` | 注意 `center` 与端点缺测 |
| `smth9_Wrap` | `scipy.ndimage.gaussian_filter` | **只是近似，不等价**；要严格复现需照抄 9 点权重 |
| `month_to_season(x, "DJF")` | `geocat.comp.month_to_season` 或 `resample("QS-DEC")` | DJF 跨年，注意年份标记 |
| `clmMonTLL(x)` | `x.groupby("time.month").mean()` | 气候态 |
| `anomMonTLL` / `rmMonAnnCycTLL` | `x.groupby("time.month") - climatology` | 去季节循环 |
| `calcMonAnomTLL` | 同上 | — |

## 三、插值与垂直坐标

| NCL | Python | 备注 |
|---|---|---|
| `vinth2p` | `geocat.comp.interp_hybrid_to_pressure` | 混合坐标 → 等压面 |
| `linint2_Wrap` | `xr.interp` 或 `xesmf.Regridder(..., "bilinear")` | 经纬度规则网格 |
| `area_conserve_remap_Wrap` | `xesmf.Regridder(..., "conservative")` | 通量类变量用守恒插值 |
| `dim_avg_n` 求纬向平均 | `.mean("lon")` | 若要面积加权，先乘 `cos(lat)` |

## 四、绘图

| NCL | Python | 备注 |
|---|---|---|
| `gsn_csm_contour_map` | `cartopy` + `ax.contourf` + `ax.coastlines()` | 投影、色标要自己搭 |
| `gsn_csm_contour` | `ax.contourf` | 纬向平均、剖面 |
| `gsn_csm_vector_map` | `ax.quiver` | 注意稀疏化 `quiverkey` |
| `gsn_define_colormap` | `matplotlib` colormap 或 `cmocean` | NCL 色表可导出为 `.rgb` 后注册 |
| `gsn_add_shapefile_polylines` | `ax.add_geometries` | cartopy 直接读 shapefile |
| `overlay` | 同一个 `ax` 多次绘制 / `fig.add_axes` | — |
| `gsn_panel` | `plt.subplots` + `gridspec` | — |

## 五、翻译工作流（推荐）

1. **先看清数据**：`ncdump -h file.nc`，确认维名、维序、单位、缺测值。
2. **按三段拆**：读入 → 计算 → 绘图。**逐段翻译、逐段验证**，不要整段丢给 AI 一把梭。
3. **每段自测**：把中间结果打印成小数组（形状 + 前几个值），和 NCL `printVarSummary` 的输出对照。
4. **绘图最后做**：NCL 出图好看是因为默认样式好，Python 要自己调；先保证数值对，再调美观。
5. **命名维**：xarray 里先把维名统一（`time, lat, lon, level`），后面所有运算都靠名字，不靠位置。

## 六、三个高频陷阱

- **维序**：NCL 的 `(time, lev, lat, lon)` 在 Python 里可能是任意顺序，一律用维名索引。
- **`regCoef_n` 的参数顺序**：`regCoef_n(x, y)` 里 x 是自变量。写成"回归海冰到 ENSO"时，
  NCL 和 `scipy.stats.linregress(x, y)` 顺序一致，但中文表述"对……做回归"极易反向。
- **缺测传播**：NCL 大量函数默认跳过 `_FillValue`，numpy 会传播 NaN。需要显式 `np.nanmean`
  或 `xarray` 的 `skipna=True`。

---

## 变更记录

| 日期 | 新增/修正 | 说明 |
|---|---|---|
| 2026-11-10 | 建表 | 初版，按组里常用函数整理 |
