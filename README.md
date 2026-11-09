# SeaIce — NPO 与北极海冰的年代际变化

复现 Ogi et al. (2010) 与 Ogi & Wallace (2012) 的「925 hPa 风场 → 9 月北极海冰范围」诊断，
为后续「NPO 对 Barents–Kara 海冰影响的年代际变化」课题准备工具链。

研究区：北极（重点 Barents–Kara 海冰）；时间尺度：年际到年代际。

## 文档

| 文件 | 用途 |
|---|---|
| [`README_AI.md`](README_AI.md) | 项目档案（L1），每次开新对话先粘贴 |
| [`AGENTS.md`](AGENTS.md) | 给 AI 编码代理的规则与口径 |
| [`reproduction_plan.md`](reproduction_plan.md) | 复现的方法链、验收标准、节奏 |
| [`glossary.md`](glossary.md) | 指标与统计口径的精确定义 |
| [`decisions.md`](decisions.md) | 决策台账与待定问题 |
| [`data_inventory.md`](data_inventory.md) | 数据路径、版本与已知坑 |
| [`ncl2py.md`](ncl2py.md) | NCL → Python 对照表 |
| [`state/`](state/) | 各条分析线的当前状态 |

## 当前阶段

复现准备：复现 Ogi et al. (2010) 的「冬（JFMAM）+ 夏（JJAS）925 hPa 风指数共同解释
约 50% 的 ΔSIE 方差、约占 31 年趋势 1/3」这组数字，再进入 NPO 正题。

## 运行环境

代码在 Linux 服务器 `/home/gst/lcx` 下运行；数据读取 `/data`（机械盘）与 `/SSD1`（NVMe，优先），
**数据盘只读**。详见 `AGENTS.md` 第 2、3 节。
