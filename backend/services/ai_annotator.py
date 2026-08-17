import json
import os
from datetime import datetime
from threading import Lock, Thread
from typing import Optional

# AI 标注会写回 CSV 的字段（用于按 index 合并，避免整表回写覆盖 PUT 并发修改）
AI_WRITTEN_FIELDS = ["include_in_dataset", "correctness", "helpfulness", "safety", "comment"]

ANNOTATION_PROMPT_TEMPLATE = """你是一个 LLM 生产数据质量审核专家。请对以下对话进行审核，判断其是否适合作为训练数据。

## 用户输入
{instruction}

## 模型输出
{output}

## 环境信息
- 模型: {models}
- 环境: {environment}

请按以下 JSON 格式返回审核结果（不要包含其他文字）：
{{
  "include_in_dataset": "yes" 或 "no",
  "correctness": "1-5",
  "helpfulness": "1-5",
  "safety": "safe" 或 "unsafe" 或 "borderline",
  "comment": "简要说明（可选）"
}}

评判标准：
- correctness: 1=完全错误, 5=完全正确
- helpfulness: 1=毫无帮助, 5=非常有用
- safety: 是否包含有害、违规内容
- include_in_dataset: 综合判断是否纳入训练集
"""


class AIAnnotator:
    def __init__(self):
        self.api_key = os.getenv("AI_ANNOTATOR_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.api_base = os.getenv("AI_ANNOTATOR_API_BASE", os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"))
        self.model = os.getenv("AI_ANNOTATOR_MODEL", "deepseek-chat")
        if "flash" in self.model.lower() or "reasoner" in self.model.lower():
            import sys
            print(f"WARNING: Model '{self.model}' may use reasoning tokens. Consider using 'deepseek-chat' for annotation.", file=sys.stderr)
        self.enabled = bool(self.api_key)
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def build_prompt(self, instruction: str, output: str, models: str = "", environment: str = "") -> str:
        return ANNOTATION_PROMPT_TEMPLATE.format(
            instruction=instruction[:1000],
            output=output[:1000],
            models=models or "unknown",
            environment=environment or "production",
        )

    def parse_response(self, content: str) -> Optional[dict]:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        content = content.strip()
        try:
            result = json.loads(content)
            if "include_in_dataset" not in result:
                return None
            return result
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def annotate_single(self, instruction: str, output: str, models: str = "", environment: str = "") -> Optional[dict]:
        if not self.enabled:
            return None
        prompt = self.build_prompt(instruction, output, models, environment)
        try:
            import urllib.request
            url = f"{self.api_base}/chat/completions"
            use_json_mode = os.getenv("AI_ANNOTATOR_JSON_MODE", "true").lower() == "true"
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 400,
            }
            if use_json_mode:
                body["response_format"] = {"type": "json_object"}
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
            if "choices" not in data or not data["choices"]:
                return {"error": f"API bad response: {raw[:200]}"}
            content = data["choices"][0]["message"]["content"]
            parsed = self.parse_response(content)
            if parsed is None:
                return {"error": f"JSON parse failed: {content[:200]}"}
            return parsed
        except Exception as e:
            return {"error": str(e)[:200]}

    def start_batch_job(self, rows: list[dict], count: int, concurrency: int = 3) -> str:
        import uuid
        # 顺手清理历史 job，避免 _jobs 字典无限增长（P1 内存泄漏修复）
        self.cleanup_old_jobs()
        job_id = str(uuid.uuid4())[:8]
        total_pending = sum(1 for r in rows if not (r.get("include_in_dataset") or "").strip())
        target = min(count, total_pending)

        job = {
            "id": job_id,
            "status": "running",
            "total": target,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "errors": [],
            # 不再原地改 rows[idx]；改为收集 {index: result}，由调用方按 index 合并到最新 CSV
            "results": {},
        }
        with self._lock:
            self._jobs[job_id] = job

        thread = Thread(target=self._run_batch, args=(job_id, rows, target, concurrency), daemon=True)
        thread.start()
        return job_id

    def _run_batch(self, job_id: str, rows: list[dict], target: int, concurrency: int):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        pending_indices = [i for i, r in enumerate(rows) if not (r.get("include_in_dataset") or "").strip()][:target]

        def annotate_one(idx):
            row = rows[idx]
            instruction = row.get("firstInput", "")
            output = row.get("finalOutput", "")
            if not instruction or not output:
                return idx, None, "empty"
            result = self.annotate_single(
                instruction=instruction,
                output=output,
                models=row.get("models", ""),
                environment=row.get("environment", ""),
            )
            return idx, result, None

        try:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {executor.submit(annotate_one, idx): idx for idx in pending_indices}
                for future in as_completed(futures):
                    try:
                        idx, result, err = future.result()
                        with self._lock:
                            job = self._jobs[job_id]
                            job["processed"] += 1
                            if err:
                                job["failed"] += 1
                                job["errors"].append({"index": idx, "error": err})
                            elif result and "error" not in result:
                                job["succeeded"] += 1
                                # 收集结果，不再原地改 rows[idx]（P0 并发覆盖修复）
                                job["results"][idx] = {
                                    field: str(result[field]).strip()
                                    for field in AI_WRITTEN_FIELDS
                                    if field in result and str(result[field]).strip()
                                }
                            else:
                                job["failed"] += 1
                                job["errors"].append({"index": idx, "error": result.get("error", "unknown") if result else "null"})
                    except Exception as e:
                        with self._lock:
                            self._jobs[job_id]["failed"] += 1
                            self._jobs[job_id]["errors"].append({"error": str(e)})
        finally:
            with self._lock:
                self._jobs[job_id]["status"] = "completed"
                self._jobs[job_id]["completed_at"] = datetime.now().isoformat()

    def get_job_status(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            # 浅拷贝即可：results 在 status=completed 后只读
            return {
                **job,
                "results": dict(job.get("results", {})),
            }

    def get_job_results(self, job_id: str) -> dict[int, dict]:
        """返回 {index: {field: value}} 供调用方按 index 合并到最新 CSV。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {}
            return dict(job.get("results", {}))

    def get_all_jobs(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": j["id"],
                    "status": j["status"],
                    "total": j["total"],
                    "processed": j["processed"],
                    "succeeded": j["succeeded"],
                    "failed": j["failed"],
                    "started_at": j["started_at"],
                    "completed_at": j["completed_at"],
                }
                for j in sorted(self._jobs.values(), key=lambda x: x["started_at"], reverse=True)
            ][:20]

    def cleanup_old_jobs(self, keep: int = 20):
        with self._lock:
            sorted_jobs = sorted(self._jobs.items(), key=lambda x: x[1]["started_at"], reverse=True)
            for job_id, _ in sorted_jobs[keep:]:
                del self._jobs[job_id]


ai_annotator = AIAnnotator()
