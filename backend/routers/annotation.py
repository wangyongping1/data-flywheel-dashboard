import csv
import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import ANNOTATION_CSV, LANGFUSE_PIPELINE_DIR, TRAINING_DATASET_JSONL
from services.ai_annotator import AI_WRITTEN_FIELDS, ai_annotator

router = APIRouter(prefix="/api/annotation", tags=["annotation"])


# 全局 CSV 写锁：所有对 annotation_batch.csv 的读-改-写都必须在锁内完成，
# 避免 ai-batch watcher 回写与 PUT 端点并发互相覆盖（P0 修复）
_csv_write_lock = threading.Lock()

ANNOTATION_FIELDS = [
    "include_in_dataset",
    "correctness",
    "helpfulness",
    "hallucination",
    "safety",
    "expected_output",
    "comment",
]

# 与 langfuse-dataset-pipeline/scripts/03_build_training_dataset.py 对齐
_APPROVED_VALUES = {"yes", "y", "true", "1"}
_TRAINING_DATASET_CSV = LANGFUSE_PIPELINE_DIR / "training_dataset.csv"


def _read_csv() -> list[dict]:
    if not ANNOTATION_CSV.exists():
        raise HTTPException(status_code=404, detail="annotation_batch.csv not found")
    with ANNOTATION_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _build_fieldnames(rows: list[dict]) -> list[str]:
    all_fields = list(rows[0].keys()) if rows else []
    for field in ANNOTATION_FIELDS:
        if field not in all_fields:
            all_fields.append(field)
    return all_fields


def _write_csv(rows: list[dict], fieldnames: list[str]):
    """写 CSV。调用方必须持有 _csv_write_lock。"""
    backup_dir = Path(os.getenv("ANNOTATION_BACKUP_DIR", "/tmp/flywheel_backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"annotation_batch.csv.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        shutil.copy2(ANNOTATION_CSV, backup)
    except OSError:
        pass
    with ANNOTATION_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _save_and_refresh(rows: list[dict]):
    """便捷封装：在写锁内回写整表。调用方应已基于最新 rows 修改。"""
    with _csv_write_lock:
        _write_csv(rows, _build_fieldnames(rows))


def _merge_results_to_csv(results: dict[int, dict]) -> int:
    """在写锁内重读最新 CSV，按 index 只合并 AI 写入字段。返回实际合并行数。

    用于 ai-batch（异步 watcher）与 ai-batch/sync 共同的「应用标注结果」逻辑（P0+P2 修复）：
    不再回写整表旧快照，避免覆盖并发 PUT 修改。
    """
    if not results:
        return 0
    with _csv_write_lock:
        try:
            fresh_rows = _read_csv()
        except HTTPException:
            return 0  # CSV 已不存在，放弃
        applied = 0
        for idx, fields in results.items():
            if 0 <= idx < len(fresh_rows):
                fresh_rows[idx].update(fields)
                applied += 1
        if applied > 0:
            _write_csv(fresh_rows, _build_fieldnames(fresh_rows))
        return applied


@router.get("/items")
def list_annotations():
    rows = _read_csv()
    reviewed = sum(1 for r in rows if (r.get("include_in_dataset") or "").strip())
    return {
        "total": len(rows),
        "reviewed": reviewed,
        "pending": len(rows) - reviewed,
        "items": rows,
    }


@router.get("/item/{index}")
def get_annotation(index: int):
    rows = _read_csv()
    if index < 0 or index >= len(rows):
        raise HTTPException(status_code=404, detail="Index out of range")
    return {"index": index, "item": rows[index]}


@router.put("/item/{index}")
def update_annotation(index: int, body: dict):
    # 读-改-写整体加锁，避免与 ai-batch watcher / 其他 PUT 并发互相覆盖（P0 修复）
    with _csv_write_lock:
        rows = _read_csv()
        if index < 0 or index >= len(rows):
            raise HTTPException(status_code=404, detail="Index out of range")
        row = rows[index]
        for field in ANNOTATION_FIELDS:
            if field in body:
                row[field] = str(body[field])
        _write_csv(rows, _build_fieldnames(rows))
    return {"status": "ok", "index": index, "item": row}


@router.get("/review")
def get_review_batch(count: int = 10):
    rows = _read_csv()
    pending = []
    for i, row in enumerate(rows):
        if not (row.get("include_in_dataset") or "").strip():
            pending.append({"index": i, "item": row})
        if len(pending) >= count:
            break
    return {
        "total_pending": sum(1 for r in rows if not (r.get("include_in_dataset") or "").strip()),
        "batch": pending,
    }


@router.post("/ai-suggest/{index}")
def ai_suggest(index: int):
    if not ai_annotator.enabled:
        raise HTTPException(status_code=400, detail="AI annotator not configured. Set AI_ANNOTATOR_API_KEY env var.")
    rows = _read_csv()
    if index < 0 or index >= len(rows):
        raise HTTPException(status_code=404, detail="Index out of range")
    row = rows[index]
    instruction = row.get("firstInput", "")
    output = row.get("finalOutput", "")
    if not instruction or not output:
        raise HTTPException(status_code=400, detail="Empty input/output")
    result = ai_annotator.annotate_single(
        instruction=instruction,
        output=output,
        models=row.get("models", ""),
        environment=row.get("environment", ""),
    )
    if result is None:
        raise HTTPException(status_code=500, detail="AI annotation failed")
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"status": "ok", "index": index, "suggestion": result}


@router.post("/ai-batch")
def ai_batch_annotate(body: dict):
    if not ai_annotator.enabled:
        raise HTTPException(status_code=400, detail="AI annotator not configured. Set AI_ANNOTATOR_API_KEY env var.")
    count = min(int(body.get("count", 10)), 100)
    concurrency = min(int(body.get("concurrency", 3)), 5)
    rows = _read_csv()
    job_id = ai_annotator.start_batch_job(rows, count, concurrency)

    def _save_when_done():
        # 等任务结束后，重读最新 CSV，按 index 只合并 AI 写入的 5 个字段，
        # 避免旧 rows 快照覆盖批跑期间 PUT 端点写入的其他字段（P0 修复）
        import time
        while True:
            job = ai_annotator.get_job_status(job_id)
            if job and job.get("status") == "completed":
                break
            time.sleep(2)
        _merge_results_to_csv(ai_annotator.get_job_results(job_id))

    from threading import Thread
    Thread(target=_save_when_done, daemon=True).start()

    return {
        "status": "started",
        "job_id": job_id,
        "message": f"AI batch annotation started (job: {job_id})",
    }


@router.post("/ai-batch/sync")
def ai_batch_annotate_sync(body: dict):
    if not ai_annotator.enabled:
        raise HTTPException(status_code=400, detail="AI annotator not configured. Set AI_ANNOTATOR_API_KEY env var.")
    count = min(int(body.get("count", 10)), 100)
    rows = _read_csv()
    results: dict[int, dict] = {}
    errors = []
    for i, row in enumerate(rows):
        if len(results) >= count:
            break
        if (row.get("include_in_dataset") or "").strip():
            continue
        instruction = row.get("firstInput", "")
        output = row.get("finalOutput", "")
        if not instruction or not output:
            continue
        result = ai_annotator.annotate_single(
            instruction=instruction,
            output=output,
            models=row.get("models", ""),
            environment=row.get("environment", ""),
        )
        if result and "error" not in result:
            fields = {
                f: str(result[f]).strip()
                for f in AI_WRITTEN_FIELDS
                if f in result and str(result[f]).strip()
            }
            if fields:
                results[i] = fields
        elif result and "error" in result:
            errors.append({"index": i, "error": result["error"]})
    # 标注阶段不加锁（网络慢），仅在最后原子合并到最新 CSV（P0 修复）
    applied = _merge_results_to_csv(results)
    return {
        "status": "ok",
        "applied": applied,
        "errors": errors,
        "message": f"AI annotated {applied} items",
    }


@router.get("/ai-batch/status/{job_id}")
def ai_batch_status(job_id: str):
    status = ai_annotator.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.get("/ai-batch/jobs")
def ai_batch_jobs():
    return {"jobs": ai_annotator.get_all_jobs()}


@router.get("/ai-status")
def ai_status():
    return {
        "enabled": ai_annotator.enabled,
        "model": ai_annotator.model if ai_annotator.enabled else None,
        "api_base": ai_annotator.api_base if ai_annotator.enabled else None,
    }


def _build_training_example(row: dict) -> dict:
    """与 langfuse-dataset-pipeline/scripts/03_build_training_dataset.py 对齐：
    output 优先取 expected_output，否则取 finalOutput。"""
    expected_output = (row.get("expected_output") or "").strip()
    target_output = expected_output or row.get("finalOutput", "")
    return {
        "traceId": row.get("traceId", ""),
        "input": row.get("firstInput", ""),
        "output": target_output,
        "source_output": row.get("finalOutput", ""),
        "labels": {
            "correctness": row.get("correctness", ""),
            "helpfulness": row.get("helpfulness", ""),
            "hallucination": row.get("hallucination", ""),
            "safety": row.get("safety", ""),
        },
        "metadata": {
            "traceName": row.get("traceName", ""),
            "sessionId": row.get("sessionId", ""),
            "userId": row.get("userId", ""),
            "environment": row.get("environment", ""),
            "models": row.get("models", ""),
            "totalTokens": row.get("totalTokens", ""),
            "comment": row.get("comment", ""),
        },
    }


@router.post("/export")
def export_training_dataset():
    """把已采纳（include_in_dataset=yes）的标注导出为 training_dataset.jsonl/.csv。

    复用 03_build_training_dataset.py 的逻辑，使「标注完 → 点导出 → 训练」在页面上闭环。
    """
    rows = _read_csv()
    approved = [r for r in rows if (r.get("include_in_dataset") or "").strip().lower() in _APPROVED_VALUES]
    examples = [_build_training_example(r) for r in approved]

    LANGFUSE_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)

    with TRAINING_DATASET_JSONL.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    fieldnames = [
        "traceId", "input", "output", "source_output",
        "correctness", "helpfulness", "hallucination", "safety",
        "traceName", "sessionId", "userId", "environment",
        "models", "totalTokens", "comment",
    ]
    with _TRAINING_DATASET_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ex in examples:
            writer.writerow({
                "traceId": ex["traceId"],
                "input": ex["input"],
                "output": ex["output"],
                "source_output": ex["source_output"],
                "correctness": ex["labels"]["correctness"],
                "helpfulness": ex["labels"]["helpfulness"],
                "hallucination": ex["labels"]["hallucination"],
                "safety": ex["labels"]["safety"],
                "traceName": ex["metadata"]["traceName"],
                "sessionId": ex["metadata"]["sessionId"],
                "userId": ex["metadata"]["userId"],
                "environment": ex["metadata"]["environment"],
                "models": ex["metadata"]["models"],
                "totalTokens": ex["metadata"]["totalTokens"],
                "comment": ex["metadata"]["comment"],
            })

    return {
        "status": "ok",
        "approved_count": len(examples),
        "total_reviewed": sum(1 for r in rows if (r.get("include_in_dataset") or "").strip()),
        "total_candidates": len(rows),
        "jsonl_path": str(TRAINING_DATASET_JSONL),
        "csv_path": str(_TRAINING_DATASET_CSV),
        "message": f"已导出 {len(examples)} 条采纳样本到 training_dataset.jsonl",
    }


@router.get("/export/status")
def export_status():
    """检查 training_dataset.jsonl 是否已生成及基本信息。"""
    if not TRAINING_DATASET_JSONL.exists():
        return {"exists": False, "count": 0}
    count = 0
    with TRAINING_DATASET_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return {
        "exists": True,
        "count": count,
        "path": str(TRAINING_DATASET_JSONL),
        "modified_at": datetime.fromtimestamp(TRAINING_DATASET_JSONL.stat().st_mtime).isoformat(),
    }
