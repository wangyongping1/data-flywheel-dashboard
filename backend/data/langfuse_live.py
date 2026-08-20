import base64
import json
import os
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode
import http.client


class LangfuseLiveReader:
    def __init__(self):
        self.host = os.getenv("LANGFUSE_HOST", "").rstrip("/")
        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        self._token = None
        self._parsed = None
        self.last_error: str | None = None
        self.trend_partial: bool = False
        self.top_partial: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.public_key and self.secret_key)

    def _get_token(self) -> str:
        if self._token is None:
            raw = f"{self.public_key}:{self.secret_key}"
            self._token = base64.b64encode(raw.encode()).decode()
        return self._token

    def _get_conn(self) -> http.client.HTTPConnection:
        if self._parsed is None:
            self._parsed = urlparse(self.host)
        hostname = self._parsed.hostname
        port = self._parsed.port or (443 if self._parsed.scheme == "https" else 80)
        if self._parsed.scheme == "https":
            conn = http.client.HTTPSConnection(hostname, port, timeout=30)
        else:
            conn = http.client.HTTPConnection(hostname, port, timeout=30)
        return conn

    def _request(self, path: str, params: dict = None) -> dict:
        query = f"?{urlencode(params)}" if params else ""
        token = self._get_token()
        conn = self._get_conn()
        try:
            conn.request("GET", path + query, headers={"Authorization": f"Basic {token}"})
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            if resp.status == 200:
                self.last_error = None
                return json.loads(body)
            self.last_error = f"HTTP {resp.status}: {body[:200]}"
            print(f"[LangfuseLive] {self.last_error}")
            return {}
        except Exception as e:
            self.last_error = str(e)
            print(f"[LangfuseLive] API error: {self.last_error}")
            return {}
        finally:
            conn.close()

    def get_observations_page(self, page: int = 1, limit: int = 100) -> dict:
        return self._request("/api/public/observations", {"page": page, "limit": limit})

    def get_traces_page(self, page: int = 1, limit: int = 100) -> dict:
        return self._request("/api/public/traces", {"page": page, "limit": limit})

    def get_total_observations(self) -> int:
        data = self.get_observations_page(page=1, limit=1)
        return data.get("meta", {}).get("totalItems", 0)

    def get_total_traces(self) -> int:
        data = self.get_traces_page(page=1, limit=1)
        return data.get("meta", {}).get("totalItems", 0)

    def _has_error(self) -> bool:
        return bool(self.last_error)

    @staticmethod
    def _empty_kpi() -> dict:
        return {
            "total_observations": 0, "total_traces": 0, "total_sessions": 0,
            "total_tokens": 0, "total_cost": 0.0, "error_count": 0,
            "error_rate": 0.0, "last_export_at": None,
            "partial": False, "scanned": 0,
        }

    def get_kpi(self) -> dict:
        total_obs = self.get_total_observations()
        total_traces = self.get_total_traces()

        if self._has_error():
            # 任一 total 调用失败：诚实返回空 KPI（last_export_at=None），
            # 上层健康度观测分自动判 0，而不是假装「当前时刻」满分。
            return self._empty_kpi()

        total_tokens = 0
        total_cost = 0.0
        error_count = 0
        scanned = 0
        max_pages = 5
        page_size = min(100, total_obs)
        pages_needed = (total_obs + page_size - 1) // page_size if total_obs > 0 else 0
        partial = pages_needed > max_pages

        for page in range(1, min(pages_needed + 1, max_pages + 1)):
            data = self.get_observations_page(page=page, limit=page_size)
            items = data.get("data", [])
            for obs in items:
                scanned += 1
                usage = obs.get("usage", {})
                total_tokens += usage.get("total", 0) or 0
                total_cost += obs.get("calculatedTotalCost", 0) or 0
                if obs.get("level") == "ERROR":
                    error_count += 1

        now = datetime.now(timezone.utc).isoformat()
        return {
            "total_observations": total_obs,
            "total_traces": total_traces,
            "total_sessions": 0,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "error_count": error_count,
            "error_rate": round(error_count / total_traces, 4) if total_traces > 0 else 0.0,
            "last_export_at": now,
            "partial": partial,
            "scanned": scanned,
        }

    def get_observation_trend(self, bucket: str = "day") -> list[dict]:
        """按 startTime 分桶聚合 observation 级指标（与 LangfuseReader 语义对齐）。

        LangfuseReader 的 trend 来自 01 脚本的 trace_summary（trace 级：observations=该
        trace 的 observation 数，input/output/tokens/cost/errors 均从 observation 聚合）。
        此处直接按 observation 聚合保证字段语义一致：
          - traces      = 桶内唯一 traceId 数
          - observations = 桶内 observation 数
          - input/output_tokens、tokens、cost、errors 均取 observation 级值
        """
        total_items = self.get_total_observations()
        if total_items == 0:
            return []
        # 与 get_kpi 一致：最多扫 5 页（500 条），超出标 partial（诚实标注截断）
        max_pages = 5
        self.trend_partial = total_items > max_pages * 100

        buckets: dict[str, dict] = {}
        trace_ids: dict[str, dict] = {}
        page_size = 100
        pages = min((total_items + page_size - 1) // page_size, max_pages)
        for page in range(1, pages + 1):
            data = self.get_observations_page(page=page, limit=page_size)
            for obs in data.get("data", []):
                ts = obs.get("startTime") or ""
                if not ts:
                    continue
                key = ts[:10] if bucket == "day" else ts[:7]
                b = buckets.setdefault(key, {
                    "date": key, "traces": 0, "observations": 0,
                    "input_tokens": 0, "output_tokens": 0, "tokens": 0,
                    "cost": 0.0, "errors": 0,
                })
                b["observations"] += 1
                usage = obs.get("usage") or {}
                b["tokens"] += obs.get("totalTokens") or 0
                b["input_tokens"] += usage.get("input", 0) or 0
                b["output_tokens"] += usage.get("output", 0) or 0
                b["cost"] += obs.get("calculatedTotalCost") or 0
                if obs.get("level") == "ERROR":
                    b["errors"] += 1
                tid = obs.get("traceId") or ""
                if tid:
                    trace_ids.setdefault((key, tid), 0)
                    trace_ids[(key, tid)] += 1

        for (key, _tid), _n in trace_ids.items():
            buckets[key]["traces"] += 1

        return sorted(buckets.values(), key=lambda x: x["date"])

    def get_top_traces(self, limit: int = 20, sort_by: str = "totalTokens") -> list[dict]:
        data = self.get_traces_page(page=1, limit=50)
        items = data.get("data", [])
        meta_total = data.get("meta", {}).get("totalItems", 0) or 0
        self.top_partial = bool(meta_total) and meta_total > 50

        def _key(t):
            if sort_by == "totalTokens":
                return (t.get("usage", {}) or {}).get("total", 0) or 0
            return 0

        items.sort(key=_key, reverse=True)
        return [{
            "traceId": t.get("id", ""),
            "traceName": t.get("name", ""),
            "firstStartTime": t.get("timestamp", ""),
            "totalTokens": (t.get("usage", {}) or {}).get("total", 0) or 0,
            "totalCost": t.get("calculatedTotalCost", 0) or 0,
            "errorCount": 1 if t.get("level") == "ERROR" else 0,
        } for t in items[:limit]]
