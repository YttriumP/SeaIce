# 数据清单

> 原则：**每一份数据都能回答五个问题**——哪一版、什么变量、什么分辨率、什么时段、在哪台机器的哪个路径。
> 缺一个，半年后你就复现不出自己的图。

- **计算/工作区**：`/home/gst/lcx/SeaIce`（项目仓库；**不是** `/home/gst/lcx` 本身）
- **数据盘**：`/data`（机械盘，15 TB），`/SSD1`（NVMe SSD，优先读）
- **在线索引**：https://server.feliks.top/ （AList，游客可读；**只读，禁止删除**）

---

## 一、本项目已确认可用的数据

| 类别 | 数据集 | 服务器路径 | 变量 | 分辨率 | 时段 |
|---|---|---|---|---|---|
| 风场（复现） | NCEP/NCAR R1 | `/data/NCEP1/uwnd.mon.mean.nc` | `uwnd` @ 925 hPa | 2.5°，17 层 | 1948.01–2025.03 |
| 风场（复现） | NCEP/NCAR R1 | `/data/NCEP1/vwnd.mon.mean.nc` | `vwnd` @ 925 hPa | 2.5°，17 层 | 1948.01–2025.03 |
| SLP（NPO 指数用） | NCEP/NCAR R1 | `/data/NCEP1/slp.mon.mean.nc` | `slp` | 2.5° | 1948.01– |
| 海冰（复现） | NSIDC-0051 Bootstrap SIC | `/data/SST_SIC/NSIDC0051_SEAICE_PS_N25km_197811_202212_v2.0_regrid.nc` | `seaice_conc` | 25 km（已 regrid） | 1978.11–2022.12 |
| 海冰（备选） | NSIDC-0051 v5 | `/data/SST_SIC/sic_psn25_197811-202412_v05r00.nc` | `seaice_conc` | 25 km | 1978.11–2024.12 |
| 海冰（对照） | HadISST 2.2.2.0 | `/data/SST_SIC/HadISST.2.2.2.0_sea_ice_concentration.nc` | `sic` | 1° | 1870– |
| SST | ERSST v5 | `/data/SST_SIC/ERSST.v5.mon.mean.nc` | `sst` | 2° | 1854– |
| 再分析（后期） | ERA5 月平均 | `/data/ERA5/` | 约 40 个变量子目录 | 0.25°，37 层 | 1940–2026 |

## 二、指数库现状（重要）

`/data/indices` 只有三个文件：

| 文件 | 内容 |
|---|---|
| `AO.ASCII` | AO（CPC） |
| `NAO.1948-present.ASCII` | NAO（Li & Wang 2003） |
| `SCA.ASCII` | 斯堪的纳维亚型 |

**没有 NPO，也没有 WP。** 这意味着：

- NPO / WP 指数必须**自己算**（用 `/data/NCEP1/slp.mon.mean.nc` 或 ERA5 的 SLP）。
- 自算之前必须先定口径（`decisions.md` Q1、Q5）。
- 算完把指数序列存成 `out/` 下的 CSV，并写进本文件。

## 三、与文献的对应关系

| 文献 | 原文用的数据 | 本项目对应 |
|---|---|---|
| Ogi et al. (2010) | SIE: Comiso & Nishio (2008) 1979–2009；风场: NCEP/NCAR 925 hPa 1979–2009 | NSIDC-0051 + `/data/NCEP1/` |
| Ogi & Wallace (2012) | 同上，时段延到 2011 | 同上 |
| Cao et al. (2025) | 观测 + 模式；Zenodo 有 data&code（297 MB） | 待读原文确认 |

> Cao et al. (2025) 的数据与绘图代码：`10.5281/zenodo.15347120`。
> 卡住时可以对照，但**先自己算再看别人的代码**。

## 四、读取约定

1. **优先 `/SSD1`**：`/data/SST_SIC`、`/data/NCEP1` 等 12 个目录是 `/SSD1` 的软链接，
   物理数据在 NVMe 上；直接写 `/data/...` 也能读，但 `/data` 是机械盘，别在里面扫大目录。
2. **只读**：数据盘禁止写入、禁止删除、禁止移动。所有产物写 `/home/gst/lcx/`。
3. **认准不带 `(1)` 的文件**：NCEP1 下有 `uwnd.mon.mean (1).nc` 之类的重复下载件。
4. **先看 `ncdump -h`**：确认维度顺序、`level` 单位（hPa）、缺测值、时间轴原点。

## 五、已知的坑

- [x] `NCEP1` 的 `level` 是 17 层，925 hPa 在不在里面、索引是几 → **在，索引 = 1**
      （1000→10 hPa，`units=millibar`，`positive=down`；脚本按坐标值选，不写死索引，2026-11-10 验证）
- [ ] Bootstrap `regrid` 版的网格和掩膜与原始 EASE-Grid 不同，算 SIE 前确认格点面积
- [ ] 经度范围 0–360 还是 −180–180；北极切片跨日界线会出问题
- [ ] NCEP/NCAR 被回溯更新过，原文用的版本与你下载的不同
- [ ] `NSIDC0051_..._regrid.nc` 只到 2022.12，复现够用，延伸到最新要换文件

## 六、校验记录

| 日期 | 数据集 | 操作 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-11-10 | NCEP1 / SST_SIC | 确认路径存在 | 通过 | 待读 `ncdump -h` |
| 2026-11-10 | NCEP1 `uwnd`/`vwnd` | `ncdump -h` + 跑通 `scripts/01_load_ncep.py` | **通过** | 层表 17 层、925 = 索引 1；938 月（1948-01→2026-02）；切片 372 月、31 个 9 月、逐月连续；u/v 零缺测；风速最大 21.86 m/s（u）、18.35 m/s（v）；产物 `out/ncep925_uv_1979_2009.nc`（31.3 MB） |
| — | NSIDC-0051 `regrid` 版 | 读 `ncdump -h`，定格点面积/阈值口径 | **未做** | 02 的前置；要看 lat/lon 是 1D 还是 2D、有无 `cell_area`、`units`、`time` 分辨率 |
