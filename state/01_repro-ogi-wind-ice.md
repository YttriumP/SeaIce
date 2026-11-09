# 01_repro-ogi-wind-ice

> 当前唯一在推进的分析线。格式说明见 `00_TEMPLATE.md`，格式示例见 `98_example_*.md`。

## 基本信息

- **编号 / 名称**：`01_repro_ogi-wind-ice`
- **状态**：进行中——**步骤 1（风场入口）已跑通**，步骤 2（SIE 序列）待写
- **一句话目标**：复现 Ogi et al. (2010) 的关键数字——冬夏风指数对 ΔSIE 的方差解释率（≈50%）
  与对 31 年趋势的贡献（≈1/3），以及 Ogi & Wallace (2012) 的反事实结论。
- **对应对话**：`#01 复现 Ogi 风场–海冰`（本文件）→ `#02 Bootstrap SIC → 9 月 SIE`
- **最后更新**：2026-11-10

## 数据与口径

- 风场：`/data/NCEP1/uwnd.mon.mean.nc`、`vwnd.mon.mean.nc`（物理在 `/SSD1`），925 hPa，月平均
- 海冰：`/data/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc`（Bootstrap SIC）
- 9 月 SIE 年序列，1979–2009（31 年）
- ΔSIE = 当年 9 月 SIE − 上一年 9 月 SIE（1980–2009，30 年）
- **冬季 = JFMAM，夏季 = JJAS**（不是 DJF/JJA）
- 风场**对 SIE 回归**；指数 = 风异常场投影到**相关图**上
- 完整口径：`glossary.md` 第 5 节

### 服务器实际布局（2026-11-10 实测，与 README 旧写法不同）

| 项 | 实际值 |
|---|---|
| 项目根 | `/home/gst/lcx/SeaIce`（**不是** `/home/gst/lcx`） |
| 脚本 | `/home/gst/lcx/SeaIce/scripts/` |
| 产物 | `/home/gst/lcx/SeaIce/out/` |
| 解释器 | `/usr/bin/python3`（系统 Python，**已含 xarray + netcdf4**，不需要 conda、不需要 venv） |
| 运行方式 | `cd /home/gst/lcx/SeaIce && /usr/bin/python3 scripts/01_load_ncep.py`（项目根由 `__file__` 推导，任意 cwd 均可） |

## 运行记录

| 日期 | 脚本 | 结果 | 产物 | 日志 |
|---|---|---|---|---|
| 2026-11-10 | `scripts/01_load_ncep.py` | **通过**（退出码 0） | `out/ncep925_uv_1979_2009.nc`（31.3 MB） | `logs/01_load_ncep_20261110.log` |
| — | `scripts/02_sept_sie.py` | 未开始 | `out/sie_sep.csv`、`out/dsie.csv` | — |

## 已验证的事实（回归时用这些判对错）

1. `level` 共 17 层，`units = millibar`，`positive = down`，顺序 1000→10 hPa；
   **925 hPa 的索引 = 1**。脚本按坐标值选取，索引是算出来的，不写死。
2. 原始文件 938 个月（1948-01 → 2026-02），维序 `(time, level, lat, lon)`，
   形状 `(938, 17, 73, 144)`，float32。
3. 切片 1979-01 → 2009-12 = **372 个月**，逐月连续、无重复，其中 **9 月 31 个**。
4. 925 hPa 切片后 **u、v 均零缺测**；`|u|max = 21.86 m/s`、`|v|max = 18.35 m/s`
   （均值 u 0.612、v 0.254 m/s），量级正常，没有解包错位的迹象。
5. 产物 `out/ncep925_uv_1979_2009.nc`：`u/v(time=372, lat=73, lon=144)` float32，
   `level_hpa` 标量坐标，属性记源路径与时段，回读 `allclose` 通过。

## 中间产物

| 文件 | 内容 | 生成脚本 | 状态 |
|---|---|---|---|
| `out/sie_sep.csv` | 9 月 SIE 年序列（31 行：year, sie_1e6km2） | `scripts/02_sept_sie.py` | 未生成 |
| `out/dsie.csv` | ΔSIE 年序列（30 行：year, dsie） | `scripts/02_sept_sie.py` | 未生成 |
| `out/ncep925_uv_1979_2009.nc` | 925 hPa 月平均 u/v，1979–2009 | `scripts/01_load_ncep.py` | **已生成（31.3 MB）** |
| `out/reg_925.nc` / `out/corr_925.nc` | 冬/夏风场回归图、相关图 | `scripts/04_reg_corr.py` | 未开始 |
| `out/wind_index.csv` | 标准化冬/夏风指数 | `scripts/05_wind_index.py` | 未开始 |
| `figs/01_sie_series.png` | SIE 序列 vs 原文 | — | 未开始 |
| `figs/02_reg_maps.png` | 回归/相关空间型 | — | 未开始 |

## 已确认的结论

1. **数据层已通**：925 hPa 选层、1979–2009 切片、缺测为零，三项都有硬断言，不是"看起来对"。
2. `01_load_ncep.py` 的产物可以直接当后续唯一风场入口，不必再读 1 GB 级原始文件。
3. **暂无风–冰关系结论**——回归、指数、R² 都还没算，**不要**在这里提前写"看起来像"的话。

## 已排除的可能

1. 用 NSIDC Sea Ice Index 代替 Bootstrap——口径不同，会和原文数字混在一起。
2. 用 DJF/JJA 代替 JFMAM/JJAS——季节窗口差 1–2 个月，R² 必然对不上。
3. 怀疑 925 hPa 取错层——已用层表验证：索引 1，值 925.0 hPa，量级合理。

## 未解决 / 下一步

1. **写 `scripts/02_sept_sie.py`，但还缺 SIC 文件的 `ncdump -h`**：`lat`/`lon` 是 1D 还是 2D、
   有没有 `cell_area`、`seaice_conc` 的 `units`（% 还是 1）与 `_FillValue`、`time` 是月还是日。
   这四项直接决定「格点面积」「阈值」「月份切片」怎么写。
   **若一时拿不到头信息**：写运行时探测版（打印实际网格、走哪级面积回退、判出的单位），
   把真正无法自动判定的地方标 `# TODO(待确认)`，不要用"看起来合理"的常数（如 25 km 等积格点面积 625 km²）。
2. **Q3（`decisions.md`）**：`regrid` 版（到 2022.12）还是 `sic_psn25_..._v05r00.nc`（到 2024.12）。
   先按任务指定用 `regrid` 版；两版都算出来后与原文 Fig.1 比。
3. 03 起的投影 / 相关是否用 `cos(lat)` 加权（`reproduction_plan.md` 风险表）——到时两种都算，看差异。
4. 周二面谈 Q1/Q5（NPO 与 WP 的定义），在复现做完前不动指数。

---

## 交接摘要（复制到新对话的那段）

```
【分析线 01 / 对话 #02】Bootstrap SIC → 9 月 SIE 年序列 + ΔSIE
【目标】写 scripts/02_sept_sie.py：从 Bootstrap SIC 算北极 9 月 SIE（1979–2009，31 个值），
        差分得 ΔSIE（1980–2009，30 个值），断言 len(sie)==31、len(dsie)==30，
        输出 out/sie_sep.csv（year,sie_1e6km2）与 out/dsie.csv（year,dsie）
【进度】01_load_ncep.py 已于 2026-11-10 跑通；out/ncep925_uv_1979_2009.nc 已生成
        （925 hPa 索引=1，1979-01→2009-12，372 月，31 个 9 月，u/v 零缺测，31.3 MB）。
        02 尚未开始。
【数据】/SSD1/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc（只读）
        备选 /SSD1/SST_SIC/sic_psn25_197811-202412_v05r00.nc（Q3 未定，默认用前者）
【口径】Bootstrap SIC（不是 Sea Ice Index）；extent：sic > 15% 记满格；面积加权；北极
        1979–2009 含首尾共 31 个 9 月；ΔSIE=当年−上一年；见 glossary.md §5
【待确认】SIC 的 ncdump -h：lat/lon 1D 还是 2D、有无 cell_area、units 是 % 还是 1、
          time 是月还是日、_FillValue —— 决定面积算法与阈值写法
【已排除】Sea Ice Index；用面积（浓度加权）冒充 extent；DJF/JJA 代替 JFMAM/JJAS
【环境】项目根 /home/gst/lcx/SeaIce；/usr/bin/python3 已含 xarray+netcdf4，无需 venv
【下一步】贴 SIC 文件 ncdump -h，然后写 02_sept_sie.py
```
