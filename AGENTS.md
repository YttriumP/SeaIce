# AGENTS.md

> 本文件给**在 `seaice-teleconnection/` 目录里动手干活的 AI 编码代理**看。
> 人类可读的项目档案在 `README_AI.md`；本文件只写"怎么做、不许做什么、怎么算做完"。
> 每次开新会话，先读本文件 + `state/` 下当前分析线。

---

## 1. 项目语境（一句话）

复现 Ogi et al. (2010) 与 Ogi & Wallace (2012) 的"925 hPa 风场 → 9 月北极 SIE"诊断，
为后续"NPO 对 Barents–Kara 海冰影响的年代际变化"课题准备工具。
**当前阶段：复现，不是创新。照原文，不改良。**

## 2. 运行环境

- 代码运行在 Linux 服务器，项目根 `/home/gst/lcx/SeaIce`（`/home/gst/lcx` 只是父目录）；
  路径用 `Path(__file__).resolve().parents[1]` 推，不写死
- Python 3，用 `/usr/bin/python3`（已含 `xarray` + `netcdf4`，实测不需要 venv / conda）
- 无 GUI：matplotlib 必须 `matplotlib.use("Agg")`
- 不要写 Windows 路径（`C:\...`），不要写死 `~/`，用相对项目根的路径
- 不改 `conda` 环境、不 `pip install`（除非人类明确要求）

## 3. 数据（只读，铁律）

| 用途 | 路径 |
|---|---|
| 925 hPa 风 | `/data/NCEP1/uwnd.mon.mean.nc`、`/data/NCEP1/vwnd.mon.mean.nc` |
| Bootstrap 海冰 | `/data/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc` |
| SLP（后续 NPO） | `/data/NCEP1/slp.mon.mean.nc` |

- **禁止**写入、删除、移动、重命名 `/data` 与 `/SSD1` 下任何文件
- `/data/SST_SIC` 是 `/SSD1` 的软链接；`/data` 是机械盘，**优先读 `/SSD1`**
- `NCEP1` 下有 `xxx (1).nc` 重复下载件，**认准不带 `(1)` 的**
- 读文件前先 `ncdump -h` 确认：维名、维序、`level` 单位（hPa）、`time` 原点、`_FillValue`
- 数据缺失或损坏时**报告并停下**，不要用别的文件悄悄替代

## 4. 必须遵守的口径（改口径 = 作废）

| 项 | 值 |
|---|---|
| 时段 | 1979–2009（共 **31** 个 9 月；第二篇到 2011） |
| 海冰 | **Bootstrap SIC**（Comiso & Nishio 2008 / NSIDC-0051），**不是** Sea Ice Index |
| 风场 | NCEP/NCAR R1，**925 hPa**，月平均 |
| 冬季 | **JFMAM**（1–5 月平均，不跨年） |
| 夏季 | **JJAS**（6–9 月平均，不跨年） |
| 回归方向 | **风场对 9 月 SIE 回归** |
| 风指数 | 每年风异常场**投影到相关图**（不是回归图） |
| 预测量 | **ΔSIE** = 当年 9 月 SIE − 上一年 9 月 SIE |

详细定义见 `glossary.md` §5。**不要**在代码里临时换季节窗口、换产品、换层次。

## 5. 代码与产物约定

```
scripts/NN_<动词>_<对象>.py    # 01_load_ncep.py, 02_sept_sie.py, ...
out/                           # CSV / NC 产物
figs/                          # PNG，300 dpi
logs/                          # 每次运行的日志
```

- 每个脚本：`python3 scripts/xx.py` 可直接跑通；可重复运行，结果一致
- 脚本头写：目的、输入、输出、依赖
- 打印关键自检（形状、时间范围、缺测数），不要静默失败
- 图内文字用**英文**（服务器无中文字体）；图注/注释用中文
- 产物文件名带参数（如 `sliding_corr_w15.csv`），不要覆盖同名旧结果

## 6. 当前任务（交给 L2 的第一件事）

写 `scripts/01_load_ncep.py` 与 `scripts/02_sept_sie.py`：

1. 读 925 hPa 月平均 `uwnd`/`vwnd`，切 1979–2009，确认层索引
2. 从 Bootstrap SIC 用面积加权、15% 阈值算北极 **9 月 SIE** 年序列（31 个值）
3. 输出 `out/sie_sep.csv`（31 行）与 `out/dsie.csv`（30 行）
4. 断言：`len(sie) == 31`、`len(dsie) == 30`

**验收**：SIE 序列与原文 Fig.1 目视一致；1980–2009 的 ΔSIE 无缺测。

## 7. 工作方式

1. 先复述任务 + 列出假设（层索引、面积权重、阈值、时间切片），等人类确认再写代码
2. 小步交付：一个脚本跑通再写下一个
3. 不确定的地方标 `# TODO(待确认)`，不要用"看起来合理"的常数填空
4. 涉及统计量（R²、趋势贡献）必须给出计算式与自由度
5. 引用文献/数值给出处，人类会自己核
6. 中文回答；不要生成参考文献列表

## 8. 文档索引

| 文件 | 作用 |
|---|---|
| `README_AI.md` | 项目档案（L1），人类粘贴用 |
| `reproduction_plan.md` | 复现方法链、验收标准、节奏 |
| `glossary.md` | 口径精确定义（§5 是复现口径） |
| `decisions.md` | 已定决策、待定问题（**Q1/Q5 未定前不算 NPO 指数**） |
| `data_inventory.md` | 数据路径与坑 |
| `state/01_repro-ogi-wind-ice.md` | 当前分析线状态与交接摘要 |
