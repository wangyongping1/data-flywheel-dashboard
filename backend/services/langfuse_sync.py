"""Langfuse 增量同步任务管理（后台线程 job，参照 ai_annotator 的成熟模式）。

任务在 backend 容器内直接调用 pipelines/feedback_extraction/sync_langfuse.py 的 sync_once。
容器需挂载 ./pipelines:/app/pipelines，且 PYTHONPATH 含 /app/pipelines/feedback_extraction。
"""
import os
import threading
import time
from datetime import datetime
from typing import Optional


class LangfuseSyncService:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # 单次触发（POST /api/import/langfuse）
    # ------------------------------------------------------------------ #
    def start_sync_job(self, force_full: bool = False) -> str:
        import uuid

        job_id = f"sync_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "force_full": force_full,
                "error": None,
                "result": None,
            }
        t = threading.Thread(target=self._run_job, args=(job_id, force_full), daemon=True)
        t.start()
        return job_id

    def _run_job(self, job_id: str, force_full: bool) -> None:
        try:
            from sync_langfuse import sync_once

            result = sync_once(
                host=os.getenv("LANGFUSE_HOST", ""),
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                path_prefix=os.getenv("LANGFUSE_API_PATH_PREFIX", ""),
                force_full=force_full,
            )
            with self._lock:
                self._jobs[job_id]["status"] = "ok"
                self._jobs[job_id]["result"] = result
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = str(e)
        finally:
            with self._lock:
                self._jobs[job_id]["finished_at"] = datetime.now().isoformat()

    def get_job_status(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return dict(job)

    def get_all_jobs(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": j["id"],
                    "status": j["status"],
                    "force_full": j["force_full"],
                    "started_at": j["started_at"],
                    "finished_at": j["finished_at"],
                    "error": j["error"],
                }
                for j in sorted(self._jobs.values(), key=lambda x: x["started_at"], reverse=True)
            ][:20]

    def cleanup_old_jobs(self, keep: int = 20):
        with self._lock:
            sorted_jobs = sorted(self._jobs.items(), key=lambda x: x[1]["started_at"], reverse=True)
            for job_id, _ in sorted_jobs[keep:]:
                del self._jobs[job_id]

    # ------------------------------------------------------------------ #
    # 自动调度（lifespan 启动后台线程，按 interval 循环；防重入）
    # ------------------------------------------------------------------ #
    def start_scheduler(self, interval_seconds: int = 300) -> None:
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                # 上一次未结束则跳过本轮（防重入）
                if not any(
                    j["status"] == "running"
                    for j in self._jobs.values()
                    if j.get("started_at")
                ):
                    try:
                        self.start_sync_job()
                    except Exception:
                        pass
                time.sleep(interval_seconds)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_scheduler(self) -> None:
        self._running = False


langfuse_sync = LangfuseSyncService()