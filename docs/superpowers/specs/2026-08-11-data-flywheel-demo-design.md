# Data Flywheel Demo Design

Date: 2026-08-11

## Product Positioning

Product name: 数据飞轮 Demo

Core message: 我们的模型质量会随着真实业务数据持续变好。

Primary audience: business stakeholders, executives, and customers who open the demo by themselves.

The demo should explain value before tools. It should not lead with Langfuse, Unsloth, or batch-runner. It should first show how real business feedback becomes training data, how training data supports model iteration, and how evaluation proves whether the next model version is worth shipping.

## Scope

The demo must:

- Keep imported Langfuse and evaluation data project-local under `data/`.
- Do not depend on machine-specific external source paths at runtime.
- Read existing data from referenced folders when available.
- Use clear placeholders for real integrations that are not ready.
- Mark every data module as `真实接入`, `静态快照`, `Demo 数据`, or `待接入`.
- Match the light visual style of the embedded evaluation dashboard.

The demo should not:

- Modify files in the referenced Langfuse or post-training projects.
- Pretend projected values are already real.
- Expose raw technical failures to business users.
- Turn the first screen into an engineering control panel.

## Navigation

Use five business-facing navigation tabs:

- 飞轮总览
- 真实反馈
- 数据资产
- 模型迭代
- 效果评估

The default tab is 飞轮总览.

## Visual System

Use the Agent Eval Lab visual language from the post-training dashboard:

- Page background: `#f7f7f5`.
- Black rounded brand pill: `数据飞轮 Demo`.
- Large serif hero titles using Georgia or a similar serif stack.
- Rounded pill navigation buttons.
- White cards with subtle gray borders.
- Thin shadows only where useful.
- Purple for quality.
- Yellow for time and efficiency.
- Orange for cost.
- Green for real connected or completed states.
- Gray for pending states.

Avoid the current dark engineering-dashboard look for the demo landing experience.

## Global Data Labels

Every major module should show one of these labels:

- `真实接入`: data comes from the current backend or read-only referenced directories.
- `静态快照`: data comes from exported static evaluation data.
- `Demo 数据`: value is a placeholder, projection, or sample.
- `待接入`: feature exists in the product story but is not executable in this demo.

Placeholder data is allowed only when it is clearly labeled and supports the demo story.

## Page 1: 飞轮总览

Purpose: help customers understand the value of the system within 30 seconds.

Hero copy:

- H1: 数据飞轮让模型持续变好
- Subtitle: 从真实业务反馈中发现问题、沉淀训练数据、验证模型迭代效果。
- Status line: 已接入真实观测、数据审核、训练 dry-run、评估快照。正式训练待 GPU 环境接入。

Primary health block:

- Show a large health score, for example `62 / 100`.
- Label: 飞轮已启动，训练闭环待正式 GPU 接入.
- Explanation: 分数由观测新鲜度、数据审核进度、训练状态、评估结果综合计算.

Value metric cards:

- 真实反馈池: `6,803 traces`, label `真实接入`.
- 可训练样本: `107 条`, label `真实接入`.
- 当前最佳评估: `67.1%`, label `静态快照` or `真实接入` depending on source.
- 预计质量提升: `+7.0 pts`, label `Demo 数据`.

Flywheel pipeline:

`真实反馈 -> 问题筛选 -> 人机审核 -> 训练数据 -> 模型迭代 -> 效果评估`

Node examples:

- 真实反馈: `17,504 observations / 6,803 traces`.
- 问题筛选: `300 candidates`.
- 人机审核: `300 reviewed / 107 approved`.
- 训练数据: `training_dataset.jsonl ready`.
- 模型迭代: `dry-run verified`.
- 效果评估: `8 eval runs / best 67.1%`.

Key insights:

- `107 条高价值样本已准备进入第一轮模型迭代。`
- `当前瓶颈是正式 GPU 训练环境，接入后可完成 v1 模型闭环。`
- `评估体系已能追踪准确率、耗时、成本，为上线决策提供证据。`

Next actions:

- 接入 GPU 训练环境
- 运行 v1 LoRA 正式训练
- 将 v1 模型加入评估实验
- 对比 baseline 与 v1 的质量、成本、耗时

## Page 2: 真实反馈

Purpose: prove that the flywheel starts from real business interactions, not a manually prepared slide.

Real data:

- Observation count.
- Trace count.
- Session count.
- Token count.
- Cost.
- Error rate.
- Last Langfuse export time.
- Daily trend for traces, tokens, cost, and errors.
- Top traces.

Demo data:

- Issue distribution such as 回答不完整, 事实错误, 安全边界, 工具调用失败.
- Business scenario tags such as 售前咨询, 售后支持, 复杂任务执行.

Fallback behavior:

- If real trace details are missing, show five demo feedback samples.
- The module must show `Demo 数据`.
- Replace technical errors with business copy: 当前未检测到真实反馈明细，已切换为演示样例。

Customer-facing explanation:

- 这些是真实业务交互中暴露出来的问题来源。
- 系统会从反馈中筛出值得训练的样本。

## Page 3: 数据资产

Purpose: show how real feedback becomes training-ready assets.

Real data:

- Candidate count: `300`.
- Reviewed count: `300`.
- Approved count: `107`.
- Approval rate: `35.7%`.
- Training dataset package status.
- Sample input, output, review decision, and review reason.

Interaction:

- Group samples as 推荐采纳, 需复核, 不进入训练.
- Use business-facing wording instead of raw annotation jargon.
- Rename export action to `生成训练数据包`.
- Keep the existing export capability.

Demo data:

- Data quality tiers.
- Estimated review time saved.

Fallback behavior:

- If annotation data is unavailable, show demo rows with `Demo 数据`.
- Do not show raw file path or CSV errors on the customer-facing page.

## Page 4: 模型迭代

Purpose: make it believable that the model will keep improving.

Real data:

- Dry-run records.
- Training data count.
- Training configuration summary.
- Run history.
- Latest run state.

Model version story:

- Current version: `baseline`.
- Next version: `v1 demo projection`.
- Training data: `107 条`.
- Training status: `dry-run verified`.
- Formal training: `待 GPU 接入`.

Projected comparison:

- Baseline accuracy: `67.1%`.
- v1 projected accuracy: `74.1%`, label `Demo 数据`.
- Estimated manual fallback reduction, label `Demo 数据`.
- Cost and latency changes, label `Demo 数据` or `静态快照` depending on source.

Main copy:

`训练脚本与数据已准备完成。正式训练环境接入后，可生成 v1 模型并进入评估。`

Fallback behavior:

- Lack of GPU should appear as a roadmap state, not a failure.
- The page should show `待接入`, not an error.

## Page 5: 效果评估

Purpose: prove that every model iteration can be measured before shipping.

Real or static data:

- Best accuracy.
- Average time.
- Average cost.
- Valid runs.
- Leaderboard.
- Cost and time charts.
- Langfuse trace links when present.

Implementation for demo:

- Keep the existing Agent Eval Lab iframe to reduce implementation cost.
- Add a Chinese business summary above the iframe.
- Show source label as `静态快照` when the live evaluation API is not running.
- Use `真实接入` only when the data is live or read directly from available results.

Demo data:

- Baseline vs v1 comparison area.
- v1 values must be marked as `Demo 数据`.

Longer-term option:

- Pull evaluation JSON into the main app and redraw charts using the unified style.
- This is not required for the first demo delivery.

## Data Sources

Existing backend data sources:

- `LangfuseReader` for Langfuse observation and trace data.
- `DatasetReader` for annotation and training dataset status.
- `TrainingReader` for dry-run and training run history.
- `EvalReader` for evaluation sessions and leaderboard data.

Imported data is read from project-local paths:

- `data/imports/langfuse`
- `data/outputs/langfuse_pipeline`
- `data/imports/evaluation`
- `data/outputs/evaluation`

## Health Score

Keep the current 100-point formula unless implementation reveals a strong reason to adjust it:

- Observation freshness: 25%.
- Dataset review progress: 25%.
- Training status: 25%.
- Evaluation result: 25%.

Labels:

- `80+`: 飞轮健康.
- `50-79`: 飞轮已启动，有待接入环节.
- `<50`: 飞轮未闭环.

## Projection Rules

Projected values are allowed for demo storytelling, but they must be clearly marked.

Initial projection rule:

- `预计质量提升 = 当前最佳评估 + 7.0 pts`
- Baseline accuracy: current best evaluation.
- v1 projected accuracy: baseline + 7.0 pts.

Projected fields must show `Demo 数据`.

## Empty States

If real data is missing:

- Do not expose raw stack traces, API failures, or filesystem errors.
- Show: 当前未检测到真实数据，已切换为演示样例。
- Mark the module as `Demo 数据`.

If evaluation API is not running:

- Use the existing static snapshot.
- Mark the module as `静态快照`.

If GPU training is not connected:

- Show the state as `待接入`.
- Explain that training data and script are ready.

## Acceptance Criteria

- A customer can open the homepage without explanation and understand the loop: real feedback -> training data -> model iteration -> evaluation proof.
- The first screen shows the core message, health score, four value metrics, and current bottleneck.
- Every placeholder or projection is marked as `Demo 数据`.
- Evaluation content from Agent Eval Lab remains accessible.
- The UI clearly resembles the light post-training dashboard style.
- Runtime data is read from project-local `data/` paths.
- The design can be implemented within the current React/Vite and FastAPI structure.
