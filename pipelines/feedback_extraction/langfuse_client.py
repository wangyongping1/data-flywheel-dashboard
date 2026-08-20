"""Langfuse REST API 客户端，直接拉取 observations 数据。

认证：HTTP Basic Auth (public_key : secret_key)
端点：GET /api/public/observations
分页：limit + page（Langfuse API 为 1 起始）
时间过滤：fromTimestamp / toTimestamp (ISO 8601)；增量用 fromUpdatedAt
响应：{data: [...], meta: {page, pageSize, totalItems, totalPages}}

实现：http.client 标准库（容器内 urllib 连 Langfuse 有坑，http.client 已验证可行；
不依赖 requests，保持 backend 镜像无需额外安装包）。

用法：
    client = LangfuseClient(host, public_key, secret_key, path_prefix="")
    for obs in client.fetch_observations(from_time, to_time):
        ...
    for obs in client.fetch_observations(from_updated_at=ts):
        ...
"""
from __future__ import annotations

import base64
import http.client
import json
import ssl
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


class LangfuseClient:
    """Langfuse REST API 客户端。"""

    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
        path_prefix: str = "",
        request_timeout: int = 30,
        rate_limit_delay: float = 0.2,
    ):
        self.host = host.rstrip("/")
        self.path_prefix = path_prefix.strip("/")
        self.auth_header = "Basic " + base64.b64encode(
            f"{public_key}:{secret_key}".encode()
        ).decode()
        self.request_timeout = request_timeout
        self.rate_limit_delay = rate_limit_delay
        prefix = f"/{self.path_prefix}" if self.path_prefix else ""
        self.api_base = f"{self.host}{prefix}/api/public"

    def _build_url(self, endpoint: str) -> str:
        return f"{self.api_base}/{endpoint.lstrip('/')}"

    @staticmethod
    def _parse_host(url: str) -> tuple[str, int, str, bool]:
        """把 URL 解析为 (host, port, path, is_https)。兼容 http/https。"""
        parsed = urllib.parse.urlsplit(url)
        is_https = parsed.scheme == "https"
        port = parsed.port or (443 if is_https else 80)
        return parsed.hostname or "", port, parsed.path or "/", is_https

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        url = self._build_url(endpoint)
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        host, port, path, is_https = self._parse_host(url)

        ctx = ssl.create_default_context()
        if is_https:
            conn = http.client.HTTPSConnection(
                host, port, timeout=self.request_timeout, context=ctx
            )
        else:
            conn = http.client.HTTPConnection(host, port, timeout=self.request_timeout)
        try:
            conn.request(
                "GET",
                path + ("?" + urllib.parse.urlencode(params) if params else ""),
                headers={
                    "Accept": "application/json",
                    "Authorization": self.auth_header,
                },
            )
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            if resp.status >= 400:
                raise http.client.HTTPException(f"HTTP {resp.status}: {body[:200]}")
            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)
            return json.loads(body)
        finally:
            conn.close()

    def fetch_observations(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        from_updated_at: Optional[datetime] = None,
        limit: int = 100,
    ) -> Iterator[dict]:
        """分页拉取 observations，逐条 yield。page 从 1 起（Langfuse API 1 起始）。"""
        page = 1
        total_pages = None
        while total_pages is None or page <= total_pages:
            params: dict = {"limit": limit, "page": page}
            if from_updated_at:
                params["fromUpdatedAt"] = from_updated_at.isoformat()
            elif from_time:
                params["fromTimestamp"] = from_time.isoformat()
            if to_time:
                params["toTimestamp"] = to_time.isoformat()

            data = self._request("observations", params)
            items = data.get("data", [])
            meta = data.get("meta", {})
            if total_pages is None:
                total_pages = meta.get("totalPages", 1)
                print(
                    f"Langfuse observations: {meta.get('totalItems', 0)} 条 / {total_pages} 页",
                    flush=True,
                )

            for item in items:
                yield item

            page += 1
            if not items:
                break

    def fetch_traces(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> Iterator[dict]:
        """分页拉取 traces，逐条 yield（备用，主流程不用）。page 从 1 起。"""
        page = 1
        total_pages = None
        while total_pages is None or page <= total_pages:
            params: dict = {"limit": limit, "page": page}
            if from_time:
                params["fromTimestamp"] = from_time.isoformat()
            if to_time:
                params["toTimestamp"] = to_time.isoformat()

            data = self._request("traces", params)
            items = data.get("data", [])
            meta = data.get("meta", {})
            if total_pages is None:
                total_pages = meta.get("totalPages", 1)
                print(
                    f"Langfuse traces: {meta.get('totalItems', 0)} 条 / {total_pages} 页",
                    flush=True,
                )

            for item in items:
                yield item

            page += 1
            if not items:
                break

    def test_connection(self) -> dict:
        """测试连接，拉 1 条 observation 验证凭证与路径。"""
        try:
            data = self._request("observations", {"limit": 1, "page": 1})
            return {
                "status": "ok",
                "host": self.host,
                "path_prefix": self.path_prefix,
                "api_base": self.api_base,
                "total_items": data.get("meta", {}).get("totalItems", 0),
            }
        except http.client.HTTPException as exc:
            return {
                "status": "error",
                "error": str(exc),
                "api_base": self.api_base,
            }
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc), "api_base": self.api_base}


def save_observations_json(path: Path, observations: Iterator[dict]) -> int:
    """保存 observations 为 JSON 数组格式（兼容 01 脚本的 iter_json_array 流式读取）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        file.write("[")
        first = True
        for item in observations:
            if not first:
                file.write(",")
            file.write(json.dumps(item, ensure_ascii=False))
            first = False
            count += 1
            if count % 1000 == 0:
                print(f"Fetched observations: {count}", flush=True)
        file.write("]")
    return count
