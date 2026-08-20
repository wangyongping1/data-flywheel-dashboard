import csv
import json
from datetime import datetime
from pathlib import Path

from config import LANGFUSE_EXPORT_DIR, LANGFUSE_PIPELINE_DIR


class LangfuseReader:
    def __init__(self, export_dir: Path = None, pipeline_dir: Path = None):
        self.export_dir = export_dir or LANGFUSE_EXPORT_DIR
        self.pipeline_dir = pipeline_dir or LANGFUSE_PIPELINE_DIR

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _read_csv(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def get_observation_summary(self) -> dict:
        summary_path = self.pipeline_dir / "profile_stats.json"
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        return {}

    def get_sync_cursor(self) -> dict:
        cursor_path = self.export_dir / "sync_cursor.json"
        if cursor_path.exists():
            try:
                return json.loads(cursor_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def get_trace_count(self) -> int:
        traces = self._read_csv(self.pipeline_dir / "trace_summary.csv")
        return len(traces)

    def get_trace_summary(self) -> list[dict]:
        return self._read_csv(self.pipeline_dir / "trace_summary.csv")

    def get_observation_trend(self, bucket: str = "day") -> list[dict]:
        """按 firstStartTime 时间戳分桶聚合 trace 级指标。

        bucket 目前只支持 day（生产数据跨度小，按天足够；后续可扩 hour/week）。
        返回按时间升序的 [{date, traces, observations, tokens, cost, errors}, ...]。
        """
        rows = self.get_trace_summary()
        if not rows:
            return []

        def _to_int(v) -> int:
            try:
                return int(float(v or 0))
            except (TypeError, ValueError):
                return 0

        def _to_float(v) -> float:
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0

        buckets: dict[str, dict] = {}
        for r in rows:
            ts = (r.get("firstStartTime") or "").strip()
            if not ts:
                continue
            key = ts[:10] if bucket == "day" else ts[:7]  # day → YYYY-MM-DD, month → YYYY-MM
            b = buckets.setdefault(key, {
                "date": key, "traces": 0, "observations": 0,
                "input_tokens": 0, "output_tokens": 0, "tokens": 0,
                "cost": 0.0, "errors": 0,
            })
            b["traces"] += 1
            b["observations"] += _to_int(r.get("observationCount"))
            b["input_tokens"] += _to_int(r.get("inputTokens"))
            b["output_tokens"] += _to_int(r.get("outputTokens"))
            b["tokens"] += _to_int(r.get("totalTokens"))
            b["cost"] += _to_float(r.get("totalCost"))
            b["errors"] += _to_int(r.get("errorCount"))

        return sorted(buckets.values(), key=lambda x: x["date"])

    def get_top_traces(self, limit: int = 20, sort_by: str = "totalTokens") -> list[dict]:
        """按指定指标取 top trace，用于观测页列表。"""
        rows = self.get_trace_summary()

        def _to_float(v) -> float:
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0

        rows = sorted(rows, key=lambda r: _to_float(r.get(sort_by)), reverse=True)
        keep = ["traceId", "traceName", "firstStartTime", "models", "environment",
                "observationCount", "totalTokens", "totalCost", "errorCount"]
        return [{k: r.get(k, "") for k in keep} for r in rows[:limit]]

    def get_last_export_time(self) -> str | None:
        cursor = self.get_sync_cursor()
        if cursor.get("last_sync_at"):
            return cursor["last_sync_at"]
        for name in ["observations.json", "observations_summary.csv"]:
            f = self.export_dir / name
            if f.exists():
                ts = f.stat().st_mtime
                return datetime.fromtimestamp(ts).isoformat()
        return None

    def get_total_observations(self) -> int:
        summary = self.get_observation_summary()
        return summary.get("observationCount", 0)

    def get_total_traces(self) -> int:
        summary = self.get_observation_summary()
        return summary.get("traceCount", 0)

    def get_total_sessions(self) -> int:
        summary = self.get_observation_summary()
        return summary.get("sessionCount", 0)

    def get_total_tokens(self) -> int:
        summary = self.get_observation_summary()
        return summary.get("totalTokens", 0)

    def get_total_cost(self) -> float:
        summary = self.get_observation_summary()
        return summary.get("totalCost", 0.0)

    def get_error_count(self) -> int:
        summary = self.get_observation_summary()
        return summary.get("tracesWithErrors", 0)

    def get_error_rate(self) -> float:
        traces = self.get_total_traces()
        if traces == 0:
            return 0.0
        return round(self.get_error_count() / traces, 4)

    def get_kpi(self) -> dict:
        cursor = self.get_sync_cursor()
        return {
            "total_observations": self.get_total_observations(),
            "total_traces": self.get_total_traces(),
            "total_sessions": self.get_total_sessions(),
            "total_tokens": self.get_total_tokens(),
            "total_cost": self.get_total_cost(),
            "error_count": self.get_error_count(),
            "error_rate": self.get_error_rate(),
            "last_export_at": self.get_last_export_time(),
            # 同步健康（用于 stale 判定：连续失败 > 0 视为数据过期）
            "consecutive_failures": cursor.get("consecutive_failures", 0),
            "last_sync_error": cursor.get("last_error"),
        }
