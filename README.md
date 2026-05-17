# BidKing — 竞拍之王估价辅助工具

一个 PySide6 GUI，帮我在《竞拍之王》游戏里更精确地估算仓库价值、记录每一场拍卖数据，为后续 ML 模型训练攒数据集。

## 快速开始

```bash
uv sync           # 同步依赖
uv run bidking-gui  # 启动 GUI
```

需要 Python ≥ 3.14。

## 工作流

每一局游戏 = 一个 session，每场拍卖 = 一条 record。

```
开始新游戏 → 选英雄 → 进地图 → 看道具读数 → 输入到 GUI
            ↓
       预估仓库总价 + 出价
            ↓
       拍卖结束 → 录入真实数据 → 标记完成
            ↓
       新一局拍卖 (沿用英雄，重选地图) ...
```

## 估价策略

### 数格子精算法 (Grid Actuarial)

利用「优品均格」(1000 银，便宜) 反推紫色总格数和物品数，从而推算金红剩余格数：

**输入**：
- 总格数 T (总仓储空间 25000 银)
- 蓝色总格数 B (良品扫描 1000 银)
- 白绿总格数 WG (普品扫描 500 银)
- 紫色平均格数 c (优品均格 1000 银，2 位小数)
- 紫色物品数预估 b_est (主观判断)
- 各品质单格估价 v_wg / v_b / v_p / v_jr

**反推逻辑**：道具显示的 `c` 是 `c <= a/b <= c+0.01`（其中 `a` 为紫色总格数，`b` 为紫色物品数）。脚本枚举所有合法 (a, b) 正整数对，选最接近 b_est 的 3 个候选。

**估值公式**：
```
总价值 = (T − B − WG − a) × v_jr  // 金红剩余格数估值
       + a × v_p                  // 紫色估值
       + B × v_b                  // 蓝色估值
       + WG × v_wg                // 白绿估值
```

默认单格估价基于实战经验：
| 品质 | 默认 ¥/格 |
|------|----------|
| 白绿 | 100 |
| 蓝   | 800 |
| 紫   | 2000 |
| 金红 | 20000 |

可在 GUI 中修改，会持久化到 `config.json`。

## 数据持久化

| 文件 | 内容 |
|------|------|
| `records.jsonl` | 每行一条拍卖记录 (UUID 索引)；保存时整文件覆盖重写 |
| `config.json`   | 策略默认值 (各色单格估价) |

两个文件都在项目根目录，已加入 `.gitignore`。

### 记录 schema

```json
{
  "record_id": "uuid",
  "timestamp": "2026-05-17T15:30:00",
  "session_id": "20260517-153000",
  "strategy": "数格子精算法",
  "map_id": 2401,
  "hero_id": 208,
  "inputs": {
    "T": 120, "B": 12, "WG": 30,
    "purple_avg": 1.6, "purple_count_est": 10,
    "v_wg": 100, "v_b": 800, "v_p": 2000, "v_jr": 20000
  },
  "predicted": {
    "candidates": [{"purple_total_grids": 16, "purple_count": 10,
                    "gold_red_grids": 42, "estimated_value": 884600}, ...],
    "selected_idx": 0
  },
  "bid": 750000,
  "actual": {
    "purple": {"count": 10, "total_grids": 16, "total_value": 60000},
    "gold":   {"count": 8,  "total_grids": 20, "total_value": 200000},
    "red":    [{"grids": 4, "value": 350000, "category": "珠宝", "name": "..."}, ...],
    "total_value": 1100000
  },
  "note": "复盘要点...",
  "status": "draft | bid_placed | completed"
}
```

`status` 自动升级：填了出价 → `bid_placed`；点「标记完成」→ `completed` (纳入 ML 数据集)。

## 数据分析

```python
import pandas as pd
df = pd.read_json("records.jsonl", lines=True)
done = df[df["status"] == "completed"]
done["diff_pct"] = (done["actual"].apply(lambda a: a["total_value"]) -
                    done["predicted"].apply(lambda p: p["candidates"][p["selected_idx"]]["estimated_value"])) / \
                   done["predicted"].apply(lambda p: p["candidates"][p["selected_idx"]]["estimated_value"]) * 100
```

## 项目结构

```
bidking/
├── __main__.py              # uv run bidking-gui 入口
├── gui/
│   ├── main_window.py       # 主窗口 (左右双列)
│   ├── history_window.py    # 历史记录
│   └── widgets/
│       └── red_items_table.py
├── strategies/
│   ├── base.py              # 策略抽象基类
│   └── grid_actuarial.py    # 数格子精算法
├── storage/
│   ├── records.py           # JSONL + UUID 存储
│   └── config.py            # 配置持久化
└── data/
    ├── maps.json            # 47 张地图
    └── heroes.json          # 20 个英雄
```

## 路线图

- [ ] 累计盈亏曲线、出价偏差分布图
- [ ] OpenCV 自动截屏识别 → 自动填充输入
- [ ] 更多估价策略 (e.g. 道具组合策略、ML 回归模型)
- [ ] 对手英雄、已购买道具等额外特征字段

## 游戏数据

`docs/` 目录下是游戏内的一些静态数据分析（英雄、地图、道具、AI 等），可能已过时，仅供参考。
