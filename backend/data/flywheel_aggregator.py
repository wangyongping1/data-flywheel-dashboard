import os
import threading
import time
from datetime import datetime, timedelta, timezone

from config import LANGFUSE_EXPORT_DIR, VERTICAL_EVAL_RESULTS_DIR
from data.langfuse_live import LangfuseLiveReader
from data.langfuse_reader import LangfuseReader
from data.dataset_reader import DatasetReader
from data.eval_reader import EvalReader
from data.training_reader import TrainingReader

# 数据来源标签（英文 key，前端映射到中文文案）
SOURCE_REAL = "real"                  # 真实接入
SOURCE_STATIC_SNAPSHOT = "static"     # 静态快照
SOURCE_DEMO = "demo"                  # Demo 数据
SOURCE_PENDING = "pending"           # 待接入
SOURCE_STALE = "stale"               # 数据过期

# 健康度中文文案映射
HEALTH_LABEL_TEXT = {
    "healthy": "飞轮健康",
    "partial": "飞轮已启动，训练闭环待正式 GPU 接入",
    "stalled": "飞轮未闭环",
}

# stale 判定阈值：last_sync_at 距今超过该秒数 → 观测 source 标 stale
STALE_AFTER_SECONDS = float(os.getenv("LANGFUSE_STALE_AFTER_SECONDS", "900"))

# ---- SWR 缓存（stale-while-revalidate）--------------------------------- #
# 包住观测 KPI 等重复计算：TTL 内直接返回缓存；过期时先返回旧值并后台刷新。
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = float(os.getenv("FLYWHEEL_CACHE_TTL_SECONDS", "60"))


def _cached(key: str, fn):
    """TTL 缓存 + stale-while-revalidate：过期时立即返回旧值并后台刷新。"""
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["value"]
    if entry:
        with _CACHE_LOCK:
            already = entry["refreshing"]
            entry["refreshing"] = True
        if not already:
            def _refresh():
                try:
                    value = fn()
                except Exception:
                    value = entry["value"]
                finally:
                    with _CACHE_LOCK:
                        _CACHE[key] = {"value": value, "ts": time.monotonic(), "refreshing": False}
            threading.Thread(target=_refresh, daemon=True).start()
        return entry["value"]
    value = fn()
    with _CACHE_LOCK:
        _CACHE[key] = {"value": value, "ts": time.monotonic(), "refreshing": False}
    return value


def _clear_cache() -> None:
    """清空全部 SWR 缓存（reader 切换时调用，避免旧数据残留）。"""
    with _CACHE_LOCK:
        _CACHE.clear()


class FlywheelAggregator:
    def __init__(self):
        # 三级选择：物化文件 → live reader 兜底 → 空 KPI
        # reader 不是固定单例：每次取值前 _refresh_reader() 动态检测，
        # 避免 sync_cursor.json 在 backend 启动后才首次出现/被删时需重启才切换（遗留问题2）
        self._live_reader = LangfuseLiveReader()
        self.langfuse = None
        self.langfuse_source = "none"
        self.dataset = DatasetReader()
        self.eval = EvalReader()
        self.vertical_eval = EvalReader(results_dir=VERTICAL_EVAL_RESULTS_DIR)
        self.training = TrainingReader()

    # ------------------------------------------------------------------ #
    # 首页总览：扩展为面向客户的价值展示
    # ------------------------------------------------------------------ #
    def _refresh_reader(self) -> bool:
        """动态选择 reader：sync_cursor.json 存在 → materialized；否则 live 兜底/空。

        返回是否发生切换（切换后调用方应清 SWR 缓存，避免旧 reader 数据残留）。
        """
        has_cursor = (LANGFUSE_EXPORT_DIR / "sync_cursor.json").exists()
        if has_cursor and self.langfuse_source != "materialized":
            self.langfuse = LangfuseReader()
            self.langfuse_source = "materialized"
            return True
        if not has_cursor and self.langfuse_source == "materialized":
            if self._live_reader.is_configured:
                self.langfuse = self._live_reader
                self.langfuse_source = "live"
            else:
                self.langfuse = None
                self.langfuse_source = "none"
            return True
        return False
    def _empty_obs_kpi(self) -> dict:
        return {
            "total_observations": 0, "total_traces": 0, "total_sessions": 0,
            "total_tokens": 0, "total_cost": 0.0, "error_count": 0,
            "error_rate": 0.0, "last_export_at": None,
        }

    def _obs_source(self, obs: dict) -> str:
        """观测来源标签：materialized 超期或连续失败 → stale，有数据 → real，否则 demo。

        live reader 永不 stale（每次请求实时）；materialized 由 sync 刷新。
        stale 判定两个信号（第 6 项：失败路径也会刷新 last_sync_at，单看时间会漏报）：
          1. last_export_at（=cursor.last_sync_at）距今超 STALE_AFTER_SECONDS
          2. consecutive_failures > 0（最近一轮 sync 失败，数据可能不新鲜）
        """
        if self.langfuse_source == "materialized":
            stale = False
            if obs.get("consecutive_failures", 0) > 0:
                stale = True
            else:
                last = obs.get("last_export_at")
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        last_dt = None
                    if last_dt is None or (datetime.now(timezone.utc) - last_dt).total_seconds() > STALE_AFTER_SECONDS:
                        stale = True
            if stale:
                return SOURCE_STALE
        if obs.get("total_observations", 0) > 0:
            return SOURCE_REAL
        return SOURCE_DEMO

    def _get_obs_kpi(self) -> dict:
        if self._refresh_reader():
            _clear_cache()  # reader 切换后清缓存，避免旧数据残留
        return _cached("obs_kpi", lambda: self.langfuse.get_kpi() if self.langfuse else self._empty_obs_kpi())

    def get_summary(self) -> dict:
        obs = self._get_obs_kpi()
        ds = self.dataset.get_kpi()
        ev = self.eval.get_kpi()
        tr = self.training.get_kpi()

        health = self._compute_health(obs, ds, ev, tr)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health_score": health["score"],
            "health_label": health["label"],
            "health_label_text": HEALTH_LABEL_TEXT.get(health["label"], ""),
            "health_explanation": "分数由观测新鲜度、数据审核进度、训练状态、评估结果综合计算",
            "status_line": self._build_status_line(obs, ds, ev, tr),
            # 面向客户的 4 个价值指标（带数据来源标签）
            "value_metrics": self._build_value_metrics(obs, ds, ev),
            # 投影规则：预计质量提升 = 当前最佳评估 + 7.0 pts
            "projection": self._build_projection(ev),
            # 关键洞察 & 下一步动作（设计文档规定）
            "key_insights": self._build_key_insights(ds, tr, ev),
            "next_actions": self._build_next_actions(),
            # 各阶段详情（保留向后兼容，每个 stage 增加 source 标签）
            "stages": {
                "observation": self._stage_observation(obs),
                "dataset": self._stage_dataset(ds),
                "training": self._stage_training(tr),
                "evaluation": self._stage_evaluation(ev),
            },
        }

    # ------------------------------------------------------------------ #
    # 飞轮管线：业务化 6 节点
    # ------------------------------------------------------------------ #
    def get_pipeline(self) -> dict:
        obs = self._get_obs_kpi()
        ds = self.dataset.get_kpi()
        ev = self.eval.get_kpi()
        tr = self.training.get_kpi()

        total_obs = obs["total_observations"]
        total_traces = obs["total_traces"]
        candidates = ds["total_candidates"]
        reviewed = ds["total_reviewed"]
        approved = ds["total_approved"]
        eval_sessions = ev.get("total_sessions", 0)
        best_acc = ev.get("best_accuracy", 0.0)
        has_dry_run = tr.get("total_runs", 0) > 0
        completed_runs = tr.get("completed_runs", 0)

        # 判断训练数据是否已就绪
        from config import TRAINING_DATASET_JSONL
        training_ready = TRAINING_DATASET_JSONL.exists()

        stages = [
            {
                "name": "real_feedback",
                "label": "真实反馈",
                "count": total_traces,
                "detail": f"{total_obs:,} observations / {total_traces:,} traces",
                "source": self._obs_source(obs),
            },
            {
                "name": "issue_filtering",
                "label": "问题筛选",
                "count": candidates,
                "detail": f"{candidates} candidates",
                "source": SOURCE_REAL if candidates > 0 else SOURCE_DEMO,
            },
            {
                "name": "human_review",
                "label": "人机审核",
                "count": approved,
                "detail": f"{reviewed} reviewed / {approved} approved",
                "source": SOURCE_REAL if candidates > 0 else SOURCE_DEMO,
            },
            {
                "name": "training_data",
                "label": "训练数据",
                "count": approved,
                "detail": "training_dataset.jsonl ready" if training_ready else "待生成 training_dataset.jsonl",
                "source": SOURCE_REAL if training_ready else SOURCE_PENDING,
            },
            {
                "name": "model_iteration",
                "label": "模型迭代",
                "count": completed_runs,
                "detail": "dry-run verified" if has_dry_run else "未开始",
                "source": SOURCE_REAL if has_dry_run else SOURCE_PENDING,
            },
            {
                "name": "evaluation",
                "label": "效果评估",
                "count": eval_sessions,
                "detail": f"{eval_sessions} eval runs / best {best_acc:.1f}%" if best_acc > 0 else f"{eval_sessions} eval runs",
                "source": SOURCE_STATIC_SNAPSHOT if eval_sessions > 0 else SOURCE_PENDING,
            },
        ]

        bottleneck = self._find_bottleneck_v2(stages, tr)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stages": stages,
            "bottleneck": bottleneck["name"],
            "bottleneck_reason": bottleneck["reason"],
        }

    def get_events(self) -> dict:
        events = []
        evt_id = 1

        ev_sessions = self.eval.get_all_sessions()
        for session in ev_sessions[:5]:
            for r in session["results"]:
                if r["total"] == 0:
                    continue
                events.append({
                    "id": f"evt_{evt_id:03d}",
                    "timestamp": session["timestamp"],
                    "stage": "evaluation",
                    "type": "eval_completed",
                    "title": f"评估完成: {r['agent']} + {r['model']}",
                    "detail": f"{r['task']} 准确率 {r['accuracy']:.1%}",
                    "metrics": {"accuracy": r["accuracy"], "trials": r["total"]},
                })
                evt_id += 1

        ds = self.dataset.get_kpi()
        if ds["last_annotation_at"]:
            events.append({
                "id": f"evt_{evt_id:03d}",
                "timestamp": ds["last_annotation_at"],
                "stage": "dataset",
                "type": "annotation_batch",
                "title": f"标注进度 {ds['total_reviewed']}/{ds['total_candidates']}",
                "detail": f"审核进度 {ds['review_progress']:.0%}，已采纳 {ds['total_approved']} 条",
                "metrics": {"reviewed": ds["total_reviewed"], "approved": ds["total_approved"]},
            })
            evt_id += 1

        obs = self._get_obs_kpi()
        if obs["last_export_at"]:
            events.append({
                "id": f"evt_{evt_id:03d}",
                "timestamp": obs["last_export_at"],
                "stage": "observation",
                "type": "export_completed",
                "title": "Langfuse 数据导出",
                "detail": f"{obs['total_observations']:,} 条观测，{obs['total_traces']:,} 个Trace",
                "metrics": {"observations": obs["total_observations"], "traces": obs["total_traces"]},
            })

        events.sort(key=lambda e: e["timestamp"], reverse=True)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }

    def get_evaluations(self) -> dict:
        sessions = self.eval.get_all_sessions()
        leaderboard = self.eval.get_leaderboard()

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions": sessions,
            "leaderboard": leaderboard,
        }

    def get_vertical_evaluations(self) -> dict:
        """垂直业务评测集：与公共评测集（terminal-bench）并列的第二条评测轨道。

        数据格式与公共集完全一致（report.json），只是放在独立目录
        data/outputs/evaluation/vertical_results/{session}/report.json。
        无数据时 source=pending，前端展示「待接入」空态。
        """
        sessions = self.vertical_eval.get_all_sessions()
        leaderboard = self.vertical_eval.get_leaderboard()
        kpi = self.vertical_eval.get_kpi()
        source = SOURCE_REAL if sessions else SOURCE_PENDING

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "sessions": sessions,
            "leaderboard": leaderboard,
            "summary": kpi,
        }

    def get_observations(self) -> dict:
        """真实反馈页：时间趋势 + top trace 列表 + 错误/成本汇总。"""
        kpi = self._get_obs_kpi()
        if self.langfuse:
            trend = _cached("obs_trend", lambda: self.langfuse.get_observation_trend("day"))
            top_traces = _cached("obs_top", lambda: self.langfuse.get_top_traces(20, "totalTokens"))
            trend_partial = getattr(self.langfuse, "trend_partial", False)
            top_partial = getattr(self.langfuse, "top_partial", False)
        else:
            trend = []
            top_traces = []
            trend_partial = False
            top_partial = False

        total_tokens = sum(b["tokens"] for b in trend)
        total_cost = round(sum(b["cost"] for b in trend), 4)
        total_errors = sum(b["errors"] for b in trend)
        date_range = {
            "start": trend[0]["date"] if trend else None,
            "end": trend[-1]["date"] if trend else None,
        }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kpi": kpi,
            "date_range": date_range,
            "trend": trend,
            "top_traces": top_traces,
            "partial": {
                "kpi": bool(kpi.get("partial", False)),
                "trend": trend_partial,
                "top_traces": top_partial,
            },
            "summary": {
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "total_errors": total_errors,
                "buckets": len(trend),
            },
            "source": self._obs_source(kpi),
        }

    def get_training_detail(self) -> dict:
        """模型迭代页：run 历史 + 配置摘要 + baseline/v1 对比。"""
        from config import TRAINING_DIR

        kpi = self.training.get_kpi()
        config_path = TRAINING_DIR / "config.yaml"
        config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

        ev = self.eval.get_kpi()
        best_acc = ev.get("best_accuracy", 0.0)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kpi": kpi,
            "runs": kpi.get("runs_history", []),
            "latest_run": kpi.get("latest_run"),
            "config_path": str(config_path),
            "config_text": config_text,
            "projection": self._build_projection(ev),
            "baseline_accuracy": best_acc,
            "source": SOURCE_REAL if kpi.get("total_runs", 0) > 0 else SOURCE_PENDING,
        }

    # ------------------------------------------------------------------ #
    # 首页价值指标 / 投影 / 洞察 / 下一步 —— 设计文档规定
    # ------------------------------------------------------------------ #
    def _build_status_line(self, obs: dict, ds: dict, ev: dict, tr: dict) -> str:
        parts = []
        if obs.get("total_traces", 0) > 0:
            parts.append("真实观测")
        if ds.get("total_candidates", 0) > 0:
            parts.append("数据审核")
        if tr.get("total_runs", 0) > 0:
            parts.append("训练 dry-run")
        if ev.get("total_sessions", 0) > 0:
            parts.append("评估快照")

        connected = "、".join(parts) if parts else "待接入"
        formal = "正式训练待 GPU 环境接入" if tr.get("completed_runs", 0) == 0 else "正式训练已完成"
        return f"已接入{connected}。{formal}。"

    def _build_value_metrics(self, obs: dict, ds: dict, ev: dict) -> list[dict]:
        total_traces = obs.get("total_traces", 0)
        approved = ds.get("total_approved", 0)
        best_acc = ev.get("best_accuracy", 0.0)

        # 当前最佳评估的来源：评估 API 在线则 real，否则 static
        eval_source = SOURCE_STATIC_SNAPSHOT
        # 如果 eval_reader 能读到真实 sessions，标记为静态快照（设计文档允许 real 或 static）
        if ev.get("total_sessions", 0) > 0:
            eval_source = SOURCE_STATIC_SNAPSHOT  # 当前从导出文件读，属静态快照

        return [
            {
                "key": "feedback_pool",
                "label": "真实反馈池",
                "value": f"{total_traces:,}",
                "unit": "traces",
                "source": SOURCE_REAL if total_traces > 0 else SOURCE_DEMO,
            },
            {
                "key": "trainable_samples",
                "label": "可训练样本",
                "value": str(approved),
                "unit": "条",
                "source": SOURCE_REAL if approved > 0 else SOURCE_DEMO,
            },
            {
                "key": "best_eval",
                "label": "当前最佳评估",
                "value": f"{best_acc:.1f}%" if best_acc > 0 else "N/A",
                "unit": "",
                "source": eval_source if best_acc > 0 else SOURCE_PENDING,
            },
            {
                "key": "projected_gain",
                "label": "预计质量提升",
                "value": "+7.0",
                "unit": "pts",
                "source": SOURCE_DEMO,
            },
        ]

    def _build_projection(self, ev: dict) -> dict:
        """投影规则：预计质量提升 = 当前最佳评估 + 7.0 pts

        accuracy 在 eval report.json 中以百分比数值存储（如 67.12 表示 67.1%）。
        """
        baseline = ev.get("best_accuracy", 0.0)
        v1_projected = baseline + 7.0 if baseline > 0 else 0.0
        return {
            "baseline_accuracy": round(baseline, 4),
            "v1_projected_accuracy": round(v1_projected, 4),
            "projected_gain_pts": 7.0 if baseline > 0 else 0.0,
            "source": SOURCE_DEMO,
        }

    def _build_key_insights(self, ds: dict, tr: dict, ev: dict) -> list[str]:
        approved = ds.get("total_approved", 0)
        completed = tr.get("completed_runs", 0)
        best_acc = ev.get("best_accuracy", 0.0)

        insights = []
        if approved > 0:
            insights.append(f"{approved} 条高价值样本已准备进入第一轮模型迭代。")
        if completed == 0:
            insights.append("当前瓶颈是正式 GPU 训练环境，接入后可完成 v1 模型闭环。")
        if best_acc > 0:
            insights.append("评估体系已能追踪准确率、耗时、成本，为上线决策提供证据。")

        # 兜底：保证至少有 1 条洞察
        if not insights:
            insights.append("飞轮各环节正在准备中，等待真实数据接入。")
        return insights

    def _build_next_actions(self) -> list[str]:
        return [
            "接入 GPU 训练环境",
            "运行 v1 LoRA 正式训练",
            "将 v1 模型加入评估实验",
            "对比 baseline 与 v1 的质量、成本、耗时",
        ]

    # ------------------------------------------------------------------ #
    # 健康度计算（保持现有 100 分公式）
    # ------------------------------------------------------------------ #
    def _compute_health(self, obs: dict, ds: dict, ev: dict, tr: dict = None) -> dict:
        weights = {"observation": 0.25, "dataset": 0.25, "training": 0.25, "evaluation": 0.25}
        scores = {}

        last_export = obs.get("last_export_at")
        if last_export:
            try:
                export_dt = datetime.fromisoformat(last_export)
                scores["observation"] = 100 if datetime.now(timezone.utc) - export_dt < timedelta(days=7) else 50
            except (ValueError, TypeError):
                scores["observation"] = 50
        else:
            scores["observation"] = 0

        scores["dataset"] = ds["review_progress"] * 100

        if tr and tr.get("completed_runs", 0) > 0:
            scores["training"] = 100
        elif tr and tr.get("total_runs", 0) > 0:
            scores["training"] = 50
        else:
            scores["training"] = 0

        best_acc = ev.get("best_accuracy", 0.0)
        scores["evaluation"] = 100 if best_acc > 0.5 else (50 if best_acc > 0 else 0)

        total = sum(scores[k] * weights[k] for k in weights)

        if total >= 80:
            label = "healthy"
        elif total >= 50:
            label = "partial"
        else:
            label = "stalled"

        return {"score": round(total), "label": label}

    # ------------------------------------------------------------------ #
    # 各阶段详情（保留向后兼容 + source 标签）
    # ------------------------------------------------------------------ #
    def _stage_observation(self, obs: dict) -> dict:
        return {
            "status": "active" if obs["total_observations"] > 0 else "inactive",
            "source": self._obs_source(obs),
            "total_observations": obs["total_observations"],
            "total_traces": obs["total_traces"],
            "total_sessions": obs["total_sessions"],
            "total_tokens": obs["total_tokens"],
            "total_cost": obs["total_cost"],
            "error_rate": obs["error_rate"],
            "last_export_at": obs["last_export_at"],
        }

    def _stage_dataset(self, ds: dict) -> dict:
        return {
            "status": "active" if ds["total_candidates"] > 0 else "inactive",
            "source": SOURCE_REAL if ds["total_candidates"] > 0 else SOURCE_DEMO,
            "total_candidates": ds["total_candidates"],
            "total_reviewed": ds["total_reviewed"],
            "total_approved": ds["total_approved"],
            "review_progress": ds["review_progress"],
            "last_annotation_at": ds["last_annotation_at"],
        }

    def _stage_training(self, tr: dict = None) -> dict:
        if not tr:
            return {
                "status": "not_connected",
                "source": SOURCE_PENDING,
                "total_runs": 0,
                "completed_runs": 0,
                "last_run_at": None,
            }
        completed = tr.get("completed_runs", 0)
        total = tr.get("total_runs", 0)
        source = SOURCE_REAL if total > 0 else SOURCE_PENDING
        return {
            "status": tr.get("status", "not_connected"),
            "source": source,
            "total_runs": total,
            "completed_runs": completed,
            "last_run_at": tr.get("last_run_at"),
            "latest_run": tr.get("latest_run"),
        }

    def _stage_evaluation(self, ev: dict) -> dict:
        return {
            "status": "active" if ev["total_sessions"] > 0 else "inactive",
            "source": SOURCE_STATIC_SNAPSHOT if ev["total_sessions"] > 0 else SOURCE_PENDING,
            "total_sessions": ev["total_sessions"],
            "total_trials": ev["total_trials"],
            "best_accuracy": ev["best_accuracy"],
            "best_config": ev["best_config"],
            "last_eval_at": ev["last_eval_at"],
        }

    # ------------------------------------------------------------------ #
    # 瓶颈分析（适配业务化 6 节点）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_bottleneck_v2(stages: list[dict], tr: dict = None) -> dict:
        """定位飞轮瓶颈：优先报告 model_iteration（正式训练待 GPU）。"""
        # 如果训练未完成，瓶颈就是模型迭代（待 GPU）
        completed = tr.get("completed_runs", 0) if tr else 0
        if completed == 0:
            return {
                "name": "model_iteration",
                "reason": "正式训练待 GPU 环境接入，是当前飞轮闭环的最大瓶颈",
            }

        # 否则找 count 最小且非零的节点
        min_stage = None
        for s in stages:
            if s["count"] == 0:
                return {"name": s["name"], "reason": f"{s['label']}环节尚未产生数据"}
            if min_stage is None or s["count"] < min_stage["count"]:
                min_stage = s

        if min_stage:
            return {"name": min_stage["name"], "reason": f"{min_stage['label']}环节是当前飞轮瓶颈"}
        return {"name": "unknown", "reason": "未检测到瓶颈"}
