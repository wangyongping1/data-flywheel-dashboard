#!/usr/bin/env python3
"""生成 data.example/ 演示假数据（不含任何真实生产数据）。

用途：真实数据在 .gitignore 中被排除（data/、training/alpaca_dataset.json、training/runs/），
本脚本生成的 data.example/ 提交进 git，克隆后运行 scripts/init_demo_data.ps1
把 example 拷贝为 data/ 即可让 Dashboard 开箱即用。

格式逐字段对齐真实文件 schema：
- outputs/langfuse_pipeline/   ← 01/02/03 管线产物（annotation_batch.csv 等 6 个文件）
- imports/langfuse/            ← Langfuse 导出（observations*.json/csv + pipeline 脚本副本 + manifest）
- outputs|imports/evaluation/  ← 评估结果（report.json + run 明细）
- training/                    ← alpaca_dataset.json + runs/

规模与真实项目对齐：300 条标注（107 采纳 / 193 拒绝）、3 个评估 session、1 个 dry-run 训练记录。
所有 ID / 用户 / 对话内容均为明显虚构的演示数据（demo-* 前缀）。

用法：python scripts/gen_demo_data.py
"""

import csv
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "data.example"

# ---- 与真实项目对齐的规模 ----
TOTAL_TRACES = 300
APPROVED_COUNT = 107
EVAL_SESSIONS = ["2026-06-24_10-00-00", "2026-06-25_10-00-00", "2026-06-26_10-00-00"]

DEMO_SYSTEM_PROMPT = (
    "You are DemoAgent, a demonstration assistant running on the data-flywheel demo stack. "
    "All conversations you see are synthetic placeholder data for populating the dashboard."
)

# (user_msg, good_reply, bad_reply) —— 好回答用于采纳样本，差回答用于拒绝样本
CONVO_TEMPLATES = [
    (
        "帮我写一首关于春天的俳句。",
        "春风拂柳梢，\n燕子归来筑新巢，\n山色映湖光。这是一首按五七五音节创作的春季俳句演示。",
        "俳句是一种诗。这个问题与俳句无关，我来聊聊演示环境的服务器配置吧。",
    ),
    (
        "把这段演示文字总结成一句话：数据飞轮通过观测、标注、训练、评估四个环节形成闭环，持续提升模型质量。",
        "数据飞轮以「观测-标注-训练-评估」闭环持续迭代模型质量。",
        "总结就是挺好的。另外提醒你今天天气不错，适合出门。",
    ),
    (
        "给一个 add(a, b) 函数写三个单元测试。",
        "import unittest\n\nclass TestAdd(unittest.TestCase):\n    def test_positive(self):\n        self.assertEqual(add(1, 2), 3)\n    def test_negative(self):\n        self.assertEqual(add(-1, -1), -2)\n    def test_zero(self):\n        self.assertEqual(add(0, 0), 0)\n\n以上覆盖正数、负数与零三种演示场景。",
        "测试很重要，建议多写测试。具体怎么写我这里就不展开了。",
    ),
    (
        "把「数据飞轮演示」翻译成英文。",
        "Data Flywheel Demo。「数据飞轮」译作 Data Flywheel，「演示」译作 Demo，均为通用译法。",
        "英文是一种语言。Demo 这个词本身就是英文缩写，详情可参考任何一本词典。",
    ),
    (
        "写一个匹配 demo- 开头 ID 的正则表达式。",
        "^demo-[a-z0-9-]+$。^ 锚定行首，[a-z0-9-]+ 匹配小写字母、数字与连字符，$ 锚定行尾。",
        "正则表达式功能强大，可以匹配很多内容，你说的这个应该也能匹配。",
    ),
    (
        "演示表 users 有 id/name/age 三列，写一条查询年龄大于 30 的 SQL。",
        "SELECT id, name, age FROM users WHERE age > 30;",
        "SQL 数据库一般都支持查询功能，你可以查阅对应数据库的官方文档。",
    ),
    (
        "帮我起草一封演示项目的周报邮件开头。",
        "主题：数据飞轮演示项目周报\n\n各位好：\n本周演示项目完成观测接入与标注流程搭建，下一周将接入训练环节。",
        "周报邮件一般包括本周工作和下周计划。我建议你自己写一写，锻炼表达能力。",
    ),
    (
        "把列表 [3, 1, 2] 排序并解释步骤。",
        "结果为 [1, 2, 3]。步骤：先比较 3 和 1 交换得 [1,3,2]，再比较 3 和 2 交换得 [1,2,3]，此为冒泡排序一轮的演示。",
        "排序后是 [1, 2, 3]。步骤略。",
    ),
    (
        "解释一下什么是占位符（placeholder）。",
        "占位符是先占据位置、后续再填充真实内容的临时标记，例如模板里的 {name} 会在渲染时被替换成真实用户名。",
        "占位符就是一个东西。据说这个概念最早由某位 1987 年的法国学者提出（注：演示用的编造信息）。",
    ),
    (
        "看看这段演示代码有什么问题：def f(x): return x * 2",
        "代码本身能运行，但缺少文档字符串、类型标注与对非法输入的处理。演示改进版：\ndef f(x: int) -> int:\n    \"\"\"Return x doubled.\"\"\"\n    if not isinstance(x, (int, float)):\n        raise TypeError(\"x must be numeric\")\n    return x * 2",
        "这段代码写得很短，短代码一般没什么问题，可以直接上线。",
    ),
    (
        "预测一下明天某股票的涨跌。",
        "我无法预测股价涨跌，这属于不确定的金融市场行为，任何确定性预测都不可靠。如果你需要，我可以演示如何计算历史波动率。",
        "明天会涨，涨幅大约 3.7%，建议全仓买入（注：演示用的错误回答）。",
    ),
    (
        "某公司 CEO 的私人手机号是多少？",
        "这属于个人隐私信息，我不能提供，也没有可靠来源。如果你需要联系某公司，建议使用其公开的官方渠道。",
        "他的手机号是 138-xxxx-xxxx，我从一个内部通讯录里看到的（注：演示用的编造回答）。",
    ),
]

MODELS = [
    "demo-vendor/demo-chat-small:free",
    "demo-vendor/demo-chat-pro:free",
    "demo-vendor/demo-reasoner:free",
]

GOOD_COMMENTS = [
    "演示样本：回答切题、结构完整，可作为训练正例。",
    "演示样本：工具调用与推理过程合理，采纳。",
    "演示样本：内容准确且安全，适合进入训练集。",
    "演示样本：对不确定问题诚实拒绝，符合预期行为。",
]
BAD_COMMENTS = [
    "演示样本：回答跑题，未回应玩家请求，拒绝。",
    "演示样本：包含编造信息（幻觉），不适合训练。",
    "演示样本：内容过于简略，无实质帮助。",
    "演示样本：给出不负责任的建议，拒绝采纳。",
]


def _demo_time(i: int) -> datetime:
    base = datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(days=i % 10, minutes=(i * 37) % 720, seconds=(i * 13) % 60,
                            milliseconds=(i * 7) % 1000)


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _first_input(user_msg: str) -> str:
    return json.dumps({"messages": [
        {"role": "system", "content": DEMO_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]}, ensure_ascii=False)


def _final_output(reply: str) -> str:
    return json.dumps({
        "content": reply, "role": "assistant",
        "tool_calls": None, "function_call": None,
        "provider_specific_fields": None,
    }, ensure_ascii=False)


def build_traces() -> list[dict]:
    """生成 300 条确定性假 trace（annotation 与 trace_summary 共用的行源）。"""
    rng = random.Random(42)
    approved_idx = set(rng.sample(range(TOTAL_TRACES), APPROVED_COUNT))

    traces = []
    for i in range(TOTAL_TRACES):
        r = random.Random(20260810 + i)
        approved = i in approved_idx
        tpl = CONVO_TEMPLATES[i % len(CONVO_TEMPLATES)]
        user_msg, good, bad = tpl
        reply = good if approved else bad

        start = _demo_time(i)
        end = start + timedelta(seconds=round(1 + r.random() * 8, 3))
        inp_tok = 400 + (i * 137) % 5200
        out_tok = 50 + (i * 71) % 1300
        obs_cnt = 1 + (i % 3)

        traces.append({
            "traceId": f"demo-trace-{i + 1:04d}",
            "traceName": "demo-completion" if i % 5 else "LLM call 1",
            "sessionId": f"demo-session-{i % 20 + 1:02d}" if i % 7 == 0 else "",
            "userId": f"demo-user-{i % 6 + 1}" if i % 11 == 0 else "",
            "environment": "default" if i % 3 else "workspace",
            "firstStartTime": _fmt_ts(start),
            "lastEndTime": _fmt_ts(end),
            "observationCount": obs_cnt,
            "generationCount": 1 + (i % 2),
            "observationTypes": f"GENERATION:{1 + (i % 2)}" + (";SPAN:1" if obs_cnt > 2 else ""),
            "models": MODELS[i % 3],
            "inputTokens": inp_tok,
            "outputTokens": out_tok,
            "totalTokens": int((inp_tok + out_tok) * 1.3),
            "totalCost": 0.0,
            "totalLatency": round((end - start).total_seconds(), 3),
            "errorCount": 1 if r.random() < 0.18 else 0,
            "firstInput": _first_input(user_msg),
            "finalOutput": _final_output(reply),
            # ---- 标注字段（仅 annotation_batch.csv 使用）----
            "include_in_dataset": "yes" if approved else "no",
            "correctness": str(r.choice([4, 5]) if approved else r.choice([1, 2, 3])),
            "helpfulness": str(r.choice([4, 5]) if approved else r.choice([1, 2, 3])),
            "hallucination": "" if approved else r.choice(["", "", "moderate"]),
            "safety": "safe",
            "expected_output": "",
            "comment": r.choice(GOOD_COMMENTS if approved else BAD_COMMENTS),
        })
    return traces


# 与真实文件逐列对齐的表头
ANNOTATION_FIELDS = [
    "traceId", "traceName", "sessionId", "userId", "environment",
    "firstStartTime", "lastEndTime", "observationCount", "generationCount",
    "models", "inputTokens", "outputTokens", "totalTokens", "totalCost",
    "errorCount", "firstInput", "finalOutput",
    "include_in_dataset", "correctness", "helpfulness", "hallucination",
    "safety", "expected_output", "comment",
]
TRACE_FIELDS = [f for f in ANNOTATION_FIELDS if f not in (
    "include_in_dataset", "correctness", "helpfulness", "hallucination",
    "safety", "expected_output", "comment")]  # trace_summary 20 列，含 totalLatency
TRACE_FIELDS = TRACE_FIELDS[:15] + ["totalLatency"] + TRACE_FIELDS[15:]


def write_langfuse_pipeline(traces: list[dict]):
    """outputs/langfuse_pipeline/ 6 个文件（01/02/03 管线产物）。"""
    out = EXAMPLE_DIR / "outputs" / "langfuse_pipeline"
    out.mkdir(parents=True, exist_ok=True)

    with (out / "trace_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRACE_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(traces)
    with (out / "trace_summary.jsonl").open("w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps({k: t[k] for k in TRACE_FIELDS}, ensure_ascii=False) + "\n")
    with (out / "annotation_batch.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ANNOTATION_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(traces)

    # profile_stats.json —— 从 trace 行汇总（与 01 脚本口径一致）
    stats = {
        "observationCount": sum(t["observationCount"] for t in traces),
        "traceCount": len(traces),
        "sessionCount": 0,
        "generationObservationCount": sum(t["generationCount"] for t in traces),
        "tracesWithErrors": sum(1 for t in traces if t["errorCount"] > 0),
        "totalTokens": sum(t["totalTokens"] for t in traces),
        "totalCost": sum(t["totalCost"] for t in traces),
    }
    (out / "profile_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # training_dataset —— 与 backend export 端点 / 03 脚本逻辑一致
    approved = [t for t in traces if t["include_in_dataset"] == "yes"]
    examples = [{
        "traceId": t["traceId"],
        "input": t["firstInput"],
        "output": t["expected_output"] or t["finalOutput"],
        "source_output": t["finalOutput"],
        "labels": {
            "correctness": t["correctness"], "helpfulness": t["helpfulness"],
            "hallucination": t["hallucination"], "safety": t["safety"],
        },
        "metadata": {
            "traceName": t["traceName"], "sessionId": t["sessionId"],
            "userId": t["userId"], "environment": t["environment"],
            "models": t["models"], "totalTokens": str(t["totalTokens"]),
            "comment": t["comment"],
        },
    } for t in approved]
    with (out / "training_dataset.jsonl").open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    csv_fields = ["traceId", "input", "output", "source_output",
                  "correctness", "helpfulness", "hallucination", "safety",
                  "traceName", "sessionId", "userId", "environment",
                  "models", "totalTokens", "comment"]
    with (out / "training_dataset.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(csv_fields)
        for ex in examples:
            w.writerow([ex["traceId"], ex["input"], ex["output"], ex["source_output"],
                        ex["labels"]["correctness"], ex["labels"]["helpfulness"],
                        ex["labels"]["hallucination"], ex["labels"]["safety"],
                        ex["metadata"]["traceName"], ex["metadata"]["sessionId"],
                        ex["metadata"]["userId"], ex["metadata"]["environment"],
                        ex["metadata"]["models"], ex["metadata"]["totalTokens"],
                        ex["metadata"]["comment"]])


def write_langfuse_export(traces: list[dict]):
    """imports/langfuse/langfuse-export-artifacts/（Langfuse 原始导出的演示版，取前 8 条 trace）。"""
    out = EXAMPLE_DIR / "imports" / "langfuse" / "langfuse-export-artifacts"
    out.mkdir(parents=True, exist_ok=True)

    observations = []
    for t in traces[:8]:
        for k in range(t["generationCount"]):
            observations.append({
                "id": f"demo-obs-{t['traceId'][-4:]}-{k + 1}",
                "traceId": t["traceId"],
                "startTime": t["firstStartTime"],
                "endTime": t["lastEndTime"],
                "projectId": "demo-project",
                "parentObservationId": None,
                "type": "GENERATION",
                "environment": t["environment"],
                "name": t["traceName"],
                "level": "ERROR" if t["errorCount"] else "DEFAULT",
                "statusMessage": "demo error: upstream timeout" if t["errorCount"] else None,
                "version": None,
                "createdAt": t["lastEndTime"],
                "updatedAt": t["lastEndTime"],
                "model": t["models"],
                "input": json.loads(t["firstInput"]),
                "output": {"content": json.loads(t["finalOutput"])["content"], "role": "assistant"},
                "usage": {"input": t["inputTokens"], "output": t["outputTokens"],
                          "total": t["totalTokens"], "unit": "TOKENS"},
                "latency": t["totalLatency"],
            })

    payload = json.dumps(observations, indent=2, ensure_ascii=False) + "\n"
    (out / "observations.json").write_text(payload, encoding="utf-8")
    (out / "observations_preview.json").write_text(payload, encoding="utf-8")

    with (out / "observations_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "traceId", "type", "name", "environment", "startTime", "endTime",
                    "latency", "model", "inputTokens", "outputTokens", "totalTokens",
                    "totalCost", "inputPreview", "outputPreview"])
        for o in observations:
            w.writerow([o["id"], o["traceId"], o["type"], o["name"], o["environment"],
                        o["startTime"], o["endTime"], o["latency"], o["model"],
                        o["usage"]["input"], o["usage"]["output"], o["usage"]["total"],
                        0.0, o["input"]["messages"][0]["content"][:120] + "...",
                        o["output"]["content"][:120] + "..."])

    # pipeline 脚本副本（纯代码，从 data/imports 原样拷贝）
    src_scripts = ROOT / "data" / "imports" / "langfuse" / "langfuse-dataset-pipeline" / "scripts"
    if src_scripts.exists():
        dst = EXAMPLE_DIR / "imports" / "langfuse" / "langfuse-dataset-pipeline" / "scripts"
        dst.mkdir(parents=True, exist_ok=True)
        for py in src_scripts.glob("*.py"):
            shutil.copy2(py, dst / py.name)

    manifest = {
        "status": "ok",
        "source": "user-provided Langfuse import source (demo)",
        "imported_at": "2026-08-11T06:20:23.533283+00:00",
        "copied_files": 3 + len(list((EXAMPLE_DIR / "imports" / "langfuse" /
                                       "langfuse-dataset-pipeline" / "scripts").glob("*.py"))),
    }
    (EXAMPLE_DIR / "imports" / "langfuse" / "import_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# 评估结果：{task}__{agent}__{provider/model} → 指标（与 report.json 真实 schema 一致）
EVAL_PLAN = [
    # (agent, model, [(session, passed), ...]) —— total 固定 8
    ("hermes", "opencode/demo-model-a", [("2026-06-24_10-00-00", 5), ("2026-06-25_10-00-00", 6), ("2026-06-26_10-00-00", 6)]),
    ("hermes", "opencode/demo-model-b", [("2026-06-24_10-00-00", 3), ("2026-06-25_10-00-00", 4), ("2026-06-26_10-00-00", 5)]),
    ("raw",    "opencode/demo-model-a", [("2026-06-24_10-00-00", 2), ("2026-06-25_10-00-00", 3)]),
    ("raw",    "opencode/demo-model-b", [("2026-06-26_10-00-00", 2)]),
]
EVAL_TASK = "demo-bench/fix-git"


def _report_entry(passed: int, total: int = 8) -> dict:
    failed = total - passed
    acc = round(passed / total * 100, 6)
    return {
        "total": total, "passed": passed, "failed": failed, "errors": 0,
        "accuracy": acc, "ci": round(100 / total, 6),
        "avg_cost": 0.0, "total_cost": 0,
        "avg_input_tokens": float(180 + passed * 91),
        "avg_output_tokens": float(1200 + passed * 347),
        "avg_time_sec": float(120 + passed * 18),
        "avg_episodes": 0,
    }


def write_evaluation():
    """imports/evaluation/results 与 outputs/evaluation/results（内容一致，两份镜像）。"""
    for base in (EXAMPLE_DIR / "imports" / "evaluation" / "results",
                 EXAMPLE_DIR / "outputs" / "evaluation" / "results"):
        base.mkdir(parents=True, exist_ok=True)
        reports = {s: {} for s in EVAL_SESSIONS}
        for agent, model, runs in EVAL_PLAN:
            for session, passed in runs:
                key = f"{EVAL_TASK}__{agent}__{model}"
                reports[session][key] = _report_entry(passed)
                # run 明细：run1 前 passed 个 reward=1（示意），其余 0
                detail_dir = base / session / EVAL_TASK / agent / model
                detail_dir.mkdir(parents=True, exist_ok=True)
                rewards = [1.0] * passed + [0.0] * (8 - passed)
                for n, reward in enumerate(rewards[:2], 1):  # 每组保留 2 个 run 明细文件
                    (detail_dir / f"run{n}.json").write_text(json.dumps({
                        "task": EVAL_TASK, "agent": agent, "model": model,
                        "run_id": n, "reward": reward,
                        "input_tokens": 179 + n * 40, "output_tokens": 5060 - n * 130,
                        "cost_usd": None, "n_episodes": None,
                        "elapsed_sec": float(118 + n * 64), "exception": None,
                        "job_dir": f"fix-git__demo{n:04d}",
                    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                (base / session / EVAL_TASK / agent / "raw" / model).mkdir(parents=True, exist_ok=True)
                (base / session / EVAL_TASK / agent / "raw" / model / "run1.json").write_text(
                    json.dumps({"task": EVAL_TASK, "agent": agent, "model": model,
                                "run_id": 1, "reward": 1.0 if passed else 0.0},
                               indent=2) + "\n", encoding="utf-8")
        for session, report in reports.items():
            (base / session / "report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # oracle 完成标记（仅最后一个 session）
        (base / EVAL_SESSIONS[-1] / EVAL_TASK / "oracle" / "done.flag").parent.mkdir(
            parents=True, exist_ok=True)
        (base / EVAL_SESSIONS[-1] / EVAL_TASK / "oracle" / "done.flag").write_text(
            "demo oracle done\n", encoding="utf-8")

    file_count = sum(1 for p in (EXAMPLE_DIR / "imports" / "evaluation").rglob("*") if p.is_file())
    manifest = {
        "status": "ok",
        "source": "user-provided evaluation import source (demo)",
        "imported_at": "2026-08-11T06:20:23.878625+00:00",
        "copied_files": file_count + 1,
        "published_files": file_count,
    }
    (EXAMPLE_DIR / "imports" / "evaluation" / "import_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_training():
    """training/ 演示产物：alpaca_dataset.json + runs/（dry-run 记录）。"""
    approved = [t for t in TRACES if t["include_in_dataset"] == "yes"]
    alpaca = [{
        "instruction": t["firstInput"],
        "input": f"Quality: {t['helpfulness']}",
        "output": t["finalOutput"],
        "text": (f"### Instruction:\n{t['firstInput']}\n\n"
                 f"### Context:\nQuality: {t['helpfulness']}\n\n"
                 f"### Response:\n{t['finalOutput']}"),
    } for t in approved]
    tdir = EXAMPLE_DIR / "training"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "alpaca_dataset.json").write_text(
        json.dumps(alpaca, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    run_id = "2026-08-09_10-00-00"
    run_dir = tdir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    src_script = ROOT / "training" / "runs" / "2026-08-10_09-12-18" / "train_unsloth.py"
    if src_script.exists():
        shutil.copy2(src_script, run_dir / "train_unsloth.py")
    run_record = {
        "model": "unsloth/llama-3-8b",
        "command": f"python training/runs/{run_id}/train_unsloth.py",
        "dataset_path": "training/alpaca_dataset.json",
        "config": {
            "model_name": "unsloth/llama-3-8b", "training_type": "lora",
            "num_epochs": 3, "learning_rate": 0.0002, "batch_size": 2,
            "lora_r": 16, "lora_alpha": 32, "max_seq_length": 2048,
            "load_in_4bit": True,
            "dataset_path": "../data/outputs/langfuse_pipeline/training_dataset.jsonl",
            "output_dir": "training/runs", "report_to": "tensorboard",
            "enable_wandb": False, "dry_run": True,
        },
        "output_dir": f"training/runs/{run_id}/model",
        "script_path": f"training/runs/{run_id}/train_unsloth.py",
        "status": "dry_run", "metrics": {},
        "run_id": run_id,
        "recorded_at": "2026-08-09T10:00:00.000000+00:00",
    }
    (run_dir / "run.json").write_text(
        json.dumps(run_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (tdir / "runs" / "index.json").write_text(json.dumps([{
        "run_id": run_id,
        "timestamp": "2026-08-09T10:00:00.000000+00:00",
        "model": "unsloth/llama-3-8b",
        "status": "dry_run",
        "metrics": {},
    }], indent=2) + "\n", encoding="utf-8")


TRACES: list[dict] = []  # write_training 引用


def main():
    global TRACES
    if EXAMPLE_DIR.exists():
        shutil.rmtree(EXAMPLE_DIR)
        print(f"[gen] 清理旧 {EXAMPLE_DIR.name}/")

    TRACES = build_traces()
    write_langfuse_pipeline(TRACES)
    write_langfuse_export(TRACES)
    write_evaluation()
    write_training()

    approved = sum(1 for t in TRACES if t["include_in_dataset"] == "yes")
    total_files = sum(1 for p in EXAMPLE_DIR.rglob("*") if p.is_file())
    print(f"[gen] 完成：{total_files} 个文件写入 data.example/")
    print(f"[gen] 规模对齐：{len(TRACES)} 条 trace / {approved} 条采纳 / "
          f"{len(EVAL_SESSIONS)} 个评估 session / 1 个训练 dry-run")


if __name__ == "__main__":
    main()
