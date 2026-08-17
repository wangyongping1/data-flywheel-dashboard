# 评估体系产品需求（多跑分双轴评估）

Date: 2026-08-10

## 1. 背景与目标

### 1.1 业务诉求

「参与研发大模型，并提升大模型在多个通用评测集及垂直业务评测集上的效果。」

核心目标有两层：

- **业务轴**：微调后模型在 Hermes Agent 真实业务场景（浏览器自动化、工具调用、安全拒绝、多轮规划、错误恢复）上的能力**显著提升**。
- **通用轴**：微调后模型在通用能力（综合知识、数学推理、代码生成等）上**不下降**，防止灾难性遗忘。

两个轴必须同时跑分，单独看业务提升没有意义——只有证明「业务提升 + 通用不降」才允许新版上线。

### 1.2 与现状的关系

当前评估系统是静态快照模式：

- `pipelines/evaluation/import_evaluation.py` 把外部跑分结果一次性导入 `data/outputs/evaluation/results/`。
- `EvalPage.tsx` 展示排行榜（4 条历史 run，best 67.1%）。
- 没有训练后自动评估，没有回归判定，没有维度级诊断。

本 PRD 把评估从「静态展示」升级为「训练后自动跑分 + 双轴对比 + 回归门槛」的闭环。

### 1.3 非目标

- 不在本期实现 benchmark 题库的 UI 编辑器（先用文件式管理，中期再做）。
- 不在本期接入真实通用 benchmark（MMLU/CMMLU 等）——通用评测集尚未确定，本期只预留入口占位。
- 不在本期实现 pairwise 评分（模型对比）——先做绝对分评分，pairwise 留到后期。

## 2. 核心概念：双轴评估

| 轴 | 评估内容 | 评估集 | 评分方式 | 判定逻辑 |
|---|---|---|---|---|
| **业务轴** | Hermes Agent 真实业务能力 | L1 holdout + L2 自造 benchmark | LLM-as-judge（0-5 分） | 必须提升 ≥ 3% 才算「业务变强」 |
| **通用轴** | 通用能力基线 | L3 通用 benchmark（占位） | 标准化跑分（0-100 分） | 下降 > 1% 即触发回归警告 |

「+X%」一律相对**原始 base 模型**计算，不用「上一个版本」做基线——避免累积漂移。

## 3. 评估体系三层架构

```
┌─────────────────────────────────────────────────────────┐
│  训练完成（unsloth_trainer 产出 adapter）                │
└────────────────────────┬────────────────────────────────┘
                         │ 自动触发
                         ▼
┌─────────────────────────────────────────────────────────┐
│  L1 快速回归层（分钟级，每次训练必跑）                  │
│  - holdout 集（从标注里切 20-30 条，永不进训练集）      │
│  - LLM-as-judge 打分                                    │
│  - 产出：业务轴 quick score                             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  L2 深度业务层（小时级，手动触发或大版本前跑）          │
│  - 多维度分类题库（50-100 题）                          │
│  - LLM-as-judge 打分 + 规则匹配                         │
│  - 产出：业务轴维度级雷达图                              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  L3 通用能力层（占位，benchmark 待定）                  │
│  - 预留 benchmark provider 接口                         │
│  - 本期只跑占位逻辑（返回 mock 分数）                   │
│  - 产出：通用轴 score                                    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  回归判定                                                │
│  - 通用下降 > 1% → 打「回滚风险」标签，不进推荐候选     │
│  - 业务提升 < 3% → 打「无明显提升」标签                  │
│  - 两项都达标 → 打「可发布」标签                         │
└─────────────────────────────────────────────────────────┘
```

## 4. benchmark 题库设计

### 4.1 L2 题库结构（多维度分类）

题库存储在 `data/evaluations/benchmarks/business_v1.jsonl`，每行一题：

```json
{
  "id": "biz-browser-001",
  "dimension": "browser_automation",
  "difficulty": "medium",
  "instruction": "打开小红书搜索「石雕制作」并提取前 10 条评论",
  "expected_outcome": "返回包含评论作者、内容、点赞数的 JSON 数组",
  "scoring_criteria": {
    "type": "rule_and_judge",
    "rule": {
      "must_contain": ["评论", "点赞"],
      "must_call_tool": "browser_extract"
    },
    "judge_rubric": "0-5 分：5=完整提取且格式正确；3=部分提取；0=未执行或完全错误"
  },
  "tags": ["browser", "extraction", "xiaohongshu"],
  "deprecated": false
}
```

### 4.2 维度划分

| 维度 | 标识 | 题量 | 评分侧重 |
|---|---|---|---|
| 浏览器自动化 | `browser_automation` | 15 | 步骤成功率 + 步数 |
| 工具调用准确性 | `tool_calling` | 20 | 参数正确率 + 调用时机 |
| 安全/隐私拒绝 | `safety_refusal` | 15 | 是否拒绝 + 话术质量 |
| 多轮规划 | `multi_turn_planning` | 15 | 任务完成度 |
| 错误恢复 | `error_recovery` | 10 | 是否走恢复流程 + 是否成功 |
| 开放问答 | `open_qa` | 15 | 回答质量（话术 + 推理） |

总计 90 题，覆盖 Hermes Agent 真实业务场景。

### 4.3 题库维护

- **存储**：`data/evaluations/benchmarks/business_v1.jsonl`（JSONL，每行一题）
- **版本化**：题库大改时升版本号（`business_v1.jsonl` → `business_v2.jsonl`），保留历史版本以支持趋势线对比
- **编辑**：手动编辑文件，提交 git
- **防泄漏**：题库物理隔离在 `data/evaluations/benchmarks/` 下，与训练集 `data/outputs/langfuse_pipeline/training_dataset.jsonl` 完全分开；标注导出脚本（`POST /api/annotation/export`）在生成训练集时显式排除带 `holdout=true` 标记的样本

### 4.4 L1 holdout 切分

- 从已采纳的 107 条标注里按 20% 比例切出 ~20 条作为 holdout
- 标注样本 schema 新增字段 `holdout: boolean`，切分时打 `true`
- `POST /api/annotation/export` 生成训练集时**排除** `holdout=true` 的样本
- holdout 集存储在 `data/evaluations/holdout/holdout_v1.jsonl`，与训练集物理隔离

## 5. 评分流程

### 5.1 LLM-as-judge 评分

**Judge 模型**：外部更强模型（GPT-4o / Claude 3.5 Sonnet），通过 `.env` 配置：

```env
JUDGE_PROVIDER=openai  # 或 anthropic
JUDGE_MODEL=gpt-4o
JUDGE_API_KEY=sk-xxx
```

**评分流程**：

1. 评估器用待评模型（微调后的 adapter）对每道题生成回答
2. 评估器把 `{instruction, expected_outcome, model_response, scoring_criteria}` 打包成 prompt，调 judge 模型
3. judge 模型返回 0-5 分 + 评语
4. 评估器汇总每个维度的平均分，换算成百分制（×20）

**Judge prompt 模板**：

```
你是一个严格的评分裁判。请根据以下标准给模型回答打分（0-5 分）：

【题目】{instruction}
【期望结果】{expected_outcome}
【模型回答】{model_response}
【评分标准】{judge_rubric}

请返回 JSON：{"score": 0-5, "reason": "简短评语"}
```

### 5.2 规则匹配评分（任务型题目）

对 `browser_automation` / `tool_calling` 等可执行任务，先跑规则匹配：

- `must_call_tool`：模型是否调用了指定工具
- `must_contain`：回答是否包含关键词
- `must_not_contain`：回答是否避免了禁止内容

规则匹配通过 → 进入 LLM-as-judge 打分；规则匹配失败 → 直接 0 分。

### 5.3 L3 通用占位

本期 L3 只实现接口占位：

```python
# backend/services/general_benchmark.py
class GeneralBenchmarkProvider(ABC):
    @abstractmethod
    def run(self, model_path: str) -> dict:
        """返回 {benchmark_name: score}"""

class MockGeneralBenchmark(GeneralBenchmarkProvider):
    def run(self, model_path: str) -> dict:
        return {"mmlu": 65.0, "cmmlu": 68.0, "ceval": 67.0}  # 占位分数
```

未来接入真实 benchmark 时，实现新的 Provider 替换 Mock 即可。

## 6. 评估执行管线

### 6.1 触发机制

**训练后自动触发**：`unsloth_trainer.py` 训练完成后，调用评估管线：

```python
# training/unsloth_trainer.py 训练完成后
from backend.services.evaluation_runner import EvaluationRunner

runner = EvaluationRunner(
    model_path=adapter_path,
    baseline_model="deepseek-ai/deepseek-v3",  # 原始 base
    judge_config=load_judge_config(),
)
result = runner.run_all()  # L1 + L2 + L3
runner.save_result(result)  # 写入 data/outputs/evaluation/results/
```

**手动触发**：UI 上「效果评估」页加「重新评估」按钮，调 `POST /api/evaluation/run`。

### 6.2 执行环境

- **WSL2 本地 GPU**（与训练同环境）
- 评估器在 WSL2 内加载微调后的 adapter，逐题生成回答
- judge 调用走外部 API（需要网络）

### 6.3 失败重试

- 单题失败：重试 3 次，仍失败则标记 `error`，不进入均分计算
- judge 调用失败：重试 3 次，仍失败则该题记 0 分并标 `judge_error`
- 整体评估失败：保留已完成的部分结果，标记 `partial`

## 7. 回归判定

### 7.1 判定规则

| 条件 | 标签 | 是否进推荐候选 |
|---|---|---|
| 通用下降 > 1% | `rollback_risk` | ❌ |
| 业务提升 < 3% | `no_improvement` | ❌ |
| 通用下降 ≤ 1% 且业务提升 ≥ 3% | `releasable` | ✅ |
| 通用下降 ≤ 1% 且业务提升 ≥ 10% | `recommended` | ✅（自动标为推荐） |

### 7.2 推荐版本管理

- 同一时刻最多 1 个版本标 `recommended`
- 新版本拿到 `recommended` 时，自动把旧 `recommended` 降级为 `releasable`
- 所有版本全保留，趋势线可看全历史

## 8. 数据存储 schema

### 8.1 评估结果文件结构

```
data/outputs/evaluation/results/
├── 2026-08-10_14-30-00/           # 一次评估 = 一个目录
│   ├── report.json                # 汇总报告（总分 + 维度分 + 判定）
│   ├── l1_holdout.jsonl           # L1 逐题明细
│   ├── l2_business.jsonl          # L2 逐题明细
│   ├── l3_general.json            # L3 通用分数
│   └── meta.json                  # 评估元信息（model, baseline, judge, duration）
└── index.json                     # 所有评估的索引（时间倒序）
```

### 8.2 report.json schema

```json
{
  "run_id": "2026-08-10_14-30-00",
  "model": "deepseek-v3-lora-20260810",
  "baseline_model": "deepseek-ai/deepseek-v3",
  "timestamp": "2026-08-10T14:30:00+08:00",
  "duration_seconds": 1800,
  "scores": {
    "business": {
      "overall": 78.5,
      "baseline_overall": 62.0,
      "delta": 16.5,
      "dimensions": {
        "browser_automation": {"score": 82.0, "baseline": 60.0, "delta": 22.0},
        "tool_calling": {"score": 85.0, "baseline": 65.0, "delta": 20.0},
        "safety_refusal": {"score": 90.0, "baseline": 80.0, "delta": 10.0},
        "multi_turn_planning": {"score": 70.0, "baseline": 55.0, "delta": 15.0},
        "error_recovery": {"score": 65.0, "baseline": 50.0, "delta": 15.0},
        "open_qa": {"score": 78.0, "baseline": 62.0, "delta": 16.0}
      }
    },
    "general": {
      "overall": 66.5,
      "baseline_overall": 67.0,
      "delta": -0.5,
      "benchmarks": {
        "mmlu": {"score": 65.0, "baseline": 65.5, "delta": -0.5},
        "cmmlu": {"score": 68.0, "baseline": 68.5, "delta": -0.5},
        "ceval": {"score": 67.0, "baseline": 67.0, "delta": 0.0}
      }
    }
  },
  "verdict": {
    "label": "recommended",
    "business_delta": 16.5,
    "general_delta": -0.5,
    "meets_business_threshold": true,
    "meets_general_threshold": true,
    "reason": "业务提升 16.5%（≥3%），通用下降 0.5%（≤1%），达标"
  }
}
```

### 8.3 index.json schema

```json
[
  {
    "run_id": "2026-08-10_14-30-00",
    "timestamp": "2026-08-10T14:30:00+08:00",
    "model": "deepseek-v3-lora-20260810",
    "business_score": 78.5,
    "general_score": 66.5,
    "verdict": "recommended"
  }
]
```

## 9. UI 设计

### 9.1 效果评估页布局

```
┌─────────────────────────────────────────────────────────┐
│  效果评估                                                │
│  [重新评估] [导出报告]                                   │
├─────────────────────────────────────────────────────────┤
│  KPI 卡片行                                              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │业务轴   │ │通用轴   │ │当前推荐 │ │评估次数 │           │
│  │78.5    │ │66.5    │ │v20260810│ │8 次    │           │
│  │↑16.5%  │ │↓0.5%   │ │         │ │        │           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
├─────────────────────────────────────────────────────────┤
│  业务能力雷达图（6 维度）                                 │
│  ┌─────────────────────┐                                │
│  │      浏览器(82)      │                                │
│  │   /        \         │                                │
│  │ 工具(85)——规划(70)   │                                │
│  │   \        /         │                                │
│  │  安全(90) 恢复(65)   │                                │
│  │       \  /           │                                │
│  │     开放(78)         │                                │
│  └─────────────────────┘                                │
│  [当前版本] [基线] [上版本] ← 切换叠加                    │
├─────────────────────────────────────────────────────────┤
│  多版本对比表                                            │
│  ┌──────────┬──────┬──────┬──────┬──────┬──────┬─────┐ │
│  │版本      │业务  │通用  │业务Δ │通用Δ │判定  │推荐 │ │
│  ├──────────┼──────┼──────┼──────┼──────┼──────┼─────┤ │
│  │v20260810 │78.5  │66.5  │+16.5 │-0.5  │可发布 │⭐   │ │
│  │v20260803 │75.0  │66.8  │+13.0 │-0.2  │可发布 │     │ │
│  │v20260727 │62.0  │67.0  │基线  │基线  │基线   │     │ │
│  │v20260720 │60.5  │64.0  │-1.5  │-3.0  │回滚风险│     │ │
│  └──────────┴──────┴──────┴──────┴──────┴──────┴─────┘ │
│  [回滚风险] 行用红色高亮                                  │
├─────────────────────────────────────────────────────────┤
│  双轴趋势线                                              │
│  ┌─────────────────────────────────────────┐            │
│  │ 业务 ━━━━━━━━━━━━━━━━━━━ (上升)         │            │
│  │ 通用 ━━━━━━━━━━━━━━━━━━━ (平稳)         │            │
│  └─────────────────────────────────────────┘            │
│  X 轴：评估时间，Y 轴：分数                              │
└─────────────────────────────────────────────────────────┘
```

### 9.2 视觉规范

- **回归风险**行：浅红背景 `#fef2f2`，`通用Δ` 文字红色 `#dc2626`
- **推荐版本**行：浅紫背景 `#f5f3ff`，⭐ 图标
- **业务提升**：绿色 `#16a34a` 箭头
- **通用下降**：红色 `#dc2626` 箭头（即使下降 0.5% 也要标红，提醒关注）
- **雷达图**：当前版本用品牌紫色实线，基线用灰色虚线，上版本用浅紫虚线

### 9.3 交互

- **雷达图切换**：顶部 toggle 切换「当前版本 / 基线 / 上版本」叠加显示
- **对比表排序**：默认按时间倒序，支持按业务分、通用分、Δ 排序
- **趋势线缩放**：支持选时间范围（近 7 次 / 近 30 次 / 全部）
- **行点击**：点击对比表某行 → 展开该次评估的逐题明细

## 10. API 设计

### 10.1 新增端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/evaluation/overview` | 返回 KPI 卡片数据（当前业务分、通用分、推荐版本、评估次数） |
| `GET` | `/api/evaluation/runs` | 返回所有评估 run 列表（含判定标签） |
| `GET` | `/api/evaluation/runs/{run_id}` | 返回某次评估的完整 report.json |
| `GET` | `/api/evaluation/radar?run_id=xxx` | 返回雷达图数据（6 维度分数 + 基线对比） |
| `GET` | `/api/evaluation/trend?metric=business|general&range=7|30|all` | 返回趋势线数据 |
| `POST` | `/api/evaluation/run` | 手动触发评估（传入 model_path） |
| `GET` | `/api/evaluation/run/status` | 查询手动触发的评估进度 |
| `GET` | `/api/evaluation/benchmarks` | 列出 benchmark 题库（文件式读取） |

### 10.2 与现有 API 的关系

- 现有 `GET /api/flywheel/pipeline` 的「⑥ 效果评估」节点要接入新数据：`status` 从 `静态快照` 升级为 `真实接入`（当有评估 run 时）或 `待接入`（无 run 时）
- 现有 `GET /api/flywheel/health` 的健康度计算要纳入回归判定：有 `rollback_risk` 版本时扣分

## 11. 与现有代码的集成点

### 11.1 后端

| 现有文件 | 改动 |
|---|---|
| [pipelines/evaluation/import_evaluation.py](file:///c:/myfile/A-huaqing/数据飞轮/pipelines/evaluation/import_evaluation.py) | 保留作为「外部评估结果导入」入口；新增 `run_evaluation.py` 作为「自动跑分」入口 |
| [backend/routers/flywheel.py](file:///c:/myfile/A-huaqing/数据飞轮/backend/routers/flywheel.py) | 新增 `/api/evaluation/*` 端点（或单独建 `backend/routers/evaluation.py`） |
| [backend/data/flywheel_aggregator.py](file:///c:/myfile/A-huaqing/数据飞轮/backend/data/flywheel_aggregator.py) | `get_pipeline()` 的「⑥ 效果评估」节点接入新数据源 |
| [training/unsloth_trainer.py](file:///c:/myfile/A-huaqing/数据飞轮/training/unsloth_trainer.py) | 训练完成后调用 `EvaluationRunner` |
| `backend/services/ai_annotator.py` | 标注 schema 新增 `holdout` 字段；导出训练集时排除 holdout |

### 11.2 前端

| 现有文件 | 改动 |
|---|---|
| [frontend/src/components/EvalPage.tsx](file:///c:/myfile/A-huaqing/数据飞轮/frontend/src/components/EvalPage.tsx) | 重构为 KPI 卡片 + 雷达图 + 对比表 + 趋势线四段式 |
| `frontend/src/api.ts` | 新增 evaluation 相关 API 调用 |
| `frontend/src/styles.css` | 新增雷达图、回归风险高亮、推荐标记样式 |

### 11.3 新增文件

```
backend/
├── routers/
│   └── evaluation.py                    # 新增：评估相关 API
├── services/
│   ├── evaluation_runner.py             # 新增：评估执行器（L1+L2+L3 编排）
│   ├── llm_judge.py                     # 新增：LLM-as-judge 客户端
│   └── general_benchmark.py             # 新增：通用 benchmark provider（含 Mock）
├── data/
│   └── evaluation_reader.py             # 新增：读取评估结果（类比 langfuse_reader）
data/
└── evaluations/
    └── benchmarks/
        ├── business_v1.jsonl            # 新增：L2 题库（90 题）
        └── holdout/
            └── holdout_v1.jsonl         # 新增：L1 holdout 集
pipelines/
└── evaluation/
    └── run_evaluation.py                # 新增：自动跑分入口（被 unsloth_trainer 调用）
```

## 12. 分阶段交付计划

### Phase 1：数据层 + API（2 周）

- 评估结果 schema 定型（report.json / index.json）
- `evaluation_reader.py` 实现（读取评估结果）
- `/api/evaluation/overview` / `/runs` / `/runs/{id}` 三个只读 API
- L2 题库 `business_v1.jsonl` 初版（先填 30 题，覆盖 6 维度）
- 用 mock 数据填充 `data.example/outputs/evaluation/results/` 供前端联调

### Phase 2：前端展示（1 周）

- `EvalPage.tsx` 重构：KPI 卡片 + 雷达图 + 对比表 + 趋势线
- 雷达图用 Chart.js 或 Recharts 实现
- 回归风险高亮、推荐标记样式
- 交互：雷达图切换、对比表排序、行点击展开

### Phase 3：评估执行器（2 周）

- `evaluation_runner.py` 实现（L1 + L2 + L3 编排）
- `llm_judge.py` 实现（调外部 judge 模型）
- `general_benchmark.py` 实现（Mock provider）
- `run_evaluation.py` 命令行入口
- `unsloth_trainer.py` 训练后自动调用
- 回归判定逻辑实现

### Phase 4：holdout 切分 + 防泄漏（1 周）

- 标注 schema 加 `holdout` 字段
- `POST /api/annotation/export` 排除 holdout
- L1 holdout 集生成脚本
- 端到端联调：训练 → 自动评估 → 回归判定 → UI 展示

### Phase 5（未来）：通用 benchmark 接入

- 实现 `GeneralBenchmarkProvider` 真实实现（接 lm-eval-harness 或 OpenCompass）
- 通用评测集选型（MMLU / CMMLU / CEval 等）
- 跑通 L3 层

## 13. 未决事项

| 事项 | 当前决策 | 待确认 |
|---|---|---|
| 通用评测集选型 | 预留接口占位，本期用 Mock | 等 GPU 资源到位后选型 |
| L2 题库规模 | 初版 30 题，目标 90 题 | 业务专家确认题目内容 |
| judge 模型 | GPT-4o | 是否切换 Claude 3.5 或其他 |
| 业务提升阈值 | ≥ 3% | 跑过几轮后根据 baseline 调整 |
| 通用下降阈值 | ≤ 1% | 同上 |
| benchmark UI 编辑器 | 本期不做 | Phase 6 再评估 |
| pairwise 评分 | 本期不做 | Phase 7 再评估 |
| 评估结果是否入 git | `data/outputs/evaluation/` 已 gitignore | 评估结果含模型回答可能敏感，确认不入库 |

## 14. 成功指标

- **功能完整性**：训练后自动跑分，无需人工干预
- **诊断价值**：从 UI 能一眼看出「哪个业务维度提升了多少」「通用有没有下降」
- **回归保护**：通用下降 > 1% 的版本绝对不会被标为推荐
- **可扩展性**：通用 benchmark 可通过实现新 Provider 接入，不改现有代码
- **演示效果**：业务方打开效果评估页，5 秒内理解「飞轮真的让模型变好了」
