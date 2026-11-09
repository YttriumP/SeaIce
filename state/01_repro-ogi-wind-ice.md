# 01_repro-ogi-wind-ice

> 当前唯一在推进的分析线。格式说明见 `00_TEMPLATE.md`，格式示例见 `98_example_*.md`。

## 基本信息

- **编号 / 名称**：`01_repro_ogi-wind-ice`
- **状态**：进行中（准备阶段）
- **一句话目标**：复现 Ogi et al. (2010) 的关键数字——冬夏风指数对 ΔSIE 的方差解释率（≈50%）
  与对 31 年趋势的贡献（≈1/3），以及 Ogi & Wallace (2012) 的反事实结论。
- **对应对话**：`#01 复现 Ogi 风场–海冰`
- **最后更新**：2026-11-10

## 数据与口径

- 风场：`/data/NCEP1/uwnd.mon.mean.nc`、`vwnd.mon.mean.nc`，925 hPa，月平均
- 海冰：`/data/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc`（Bootstrap）
- 9 月 SIE 年序列，1979–2009（31 年）
- ΔSIE = 当年 9 月 SIE − 上一年 9 月 SIE
- **冬季 = JFMAM，夏季 = JJAS**（不是 DJF/JJA）
- 风场**对 SIE 回归**；指数 = 风异常场投影到**相关图**上
- 完整口径：`glossary.md` 第 5 节

## 中间产物（计划）

| 文件 | 内容 | 生成脚本 |
|---|---|---|
| `out/sie_sep.csv` | 9 月 SIE 年序列（31 年） | `scripts/02_sept_sie.py` |
| `out/dsie.csv` | ΔSIE 年序列（30 年） | `scripts/02_sept_sie.py` |
| `out/reg_925.nc` / `out/corr_925.nc` | 冬/夏风场回归图、相关图 | `scripts/04_reg_corr.py` |
| `out/wind_index.csv` | 标准化冬/夏风指数 | `scripts/05_wind_index.py` |
| `figs/01_sie_series.png` | SIE 序列 vs 原文 | — |
| `figs/02_reg_maps.png` | 回归/相关空间型 | — |

## 已确认的结论

1. （暂无——复现还没开始，**不要**在这里写"看起来像"的东西）

## 已排除的可能

1. 用 NSIDC Sea Ice Index 代替 Bootstrap——口径不同，会和原文数字混在一起。
2. 用 DJF/JJA 代替 JFMAM/JJAS——季节窗口差 1–2 个月，R² 必然对不上。

## 未解决 / 下一步

1. `ncdump -h` 确认 925 hPa 在 `level` 里的索引、时间轴、缺测值。
2. 比对 `NSIDC0051_..._regrid.nc` 与 `sic_psn25_..._v05r00.nc`，定用哪一个。
3. 写 `01_load_ncep.py` + `02_sept_sie.py`，先把 31 年 SIE 序列跑出来。
4. 周二面谈确认 NPO / WP 定义（`decisions.md` Q1）。

---

## 交接摘要（复制到新对话的那段）

```
【分析线 01】复现 Ogi et al. (2010) + Ogi & Wallace (2012)
【目标】复现"冬(JFMAM)+夏(JJAS) 925 hPa 风指数共同解释约 50% 的 ΔSIE 方差、
        约占 31 年趋势 1/3"这组数字
【数据口径】/data/NCEP1/uwnd|vwnd.mon.mean.nc（925 hPa, 2.5°）；
           /data/SST_SIC/NSIDC0051_...（Bootstrap SIC）；
           9 月 SIE，1979–2009；ΔSIE = 当年 − 上一年；
           冬 = JFMAM，夏 = JJAS；风场对 SIE 回归，指数 = 投影到相关图
【中间产物】out/sie_sep.csv；out/dsie.csv；out/wind_index.csv
【已确认】（复现尚未开始）
【已排除】NSIDC Sea Ice Index 替代 Bootstrap；DJF/JJA 替代 JFMAM/JJAS
【下一步】ncdump -h 确认 925 hPa 层索引，跑出 31 年 9 月 SIE 序列
```
