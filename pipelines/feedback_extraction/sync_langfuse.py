"""Langfuse 增量同步器：增量拉取 → 本地物化 → 跑 01/02/03 → 拷贝产出。

物化目录（对齐 backend/config.py 的 LANGFUSE_EXPORT_DIR）：
    data/imports/langfuse/langfuse-export-artifacts/
    ├── observations.jsonl        # 真源：一行一条 observation，按 id upsert
    ├── observations.json         # 物化 JSON 数组（01 脚本 iter_json_array 兼容，每次同步后重写）
    └── sync_cursor.json          # 水位：last_updated_at / last_sync_at / total_records / consecutive_failures

同步流程（sync_once）：
1. 读 sync_cursor.json（不存在 → backfill 模式，fromTimestamp = now - LANGFUSE_BACKFILL_DAYS 天）
2. 增量拉取：fromUpdatedAt = cursor.last_updated_at
3. 流式读现有 observations.jsonl 建 {id: record} 索引 → upsert 本次拉到的记录（同 id 覆盖）
4. 原子重写 observations.jsonl（先写 .tmp 再 os.replace）
5. 物化 observations.json（JSON 数组，全量重写）
6. 复用 fetch_and_import 的编排逻辑跑 01/02/03
7. 拷贝产出到 data/outputs/langfuse_pipeline/（后端读取目录）
8. 最后一步才更新 cursor：last_sync_at=now，last_updated_at=max(拉到记录的 updatedAt)，consecutive_failures=0
9. 任一步骤异常：cursor 不更新，仅 consecutive_failures += 1，退出码非 0 → 下轮重试（幂等）

已知限制：增量 merge 不处理 Langfuse 侧删除；建议每月跑一次 --force-full 对账。

用法：
    python pipelines/feedback_extraction/sync_langfuse.py [--force-full] [--days N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fetch_and_import import (
    PROJECT_ROOT,
    EXPORT_DIR,
    OUTPUTS_DIR,
    TARGET_OUTPUTS_DIR,
    ensure_scripts_available,
    write_temp_config,
    run_pipeline_scripts,
    copy_outputs_to_target,
    load_env_file,
)
from langfuse_client import LangfuseClient

CURSOR_PATH = EXPORT_DIR / "sync_cursor.json"
JSONL_PATH = EXPORT_DIR / "observations.jsonl"
JSON_PATH = EXPORT_DIR / "observations.json"

BACKFILL_DAYS = int(os.getenv("LANGFUSE_BACKFILL_DAYS", "90"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cursor() -> dict:
    if CURSOR_PATH.exists():
        try:
            return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def write_cursor(cursor: dict) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CURSOR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cursor, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CURSOR_PATH)


def load_existing_index() -> dict:
    """流式读现有 observations.jsonl，返回 {id: record}。"""
    index: dict = {}
    if not JSONL_PATH.exists():
        return index
    with JSONL_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec_id = record.get("id") or record.get("traceId")
            if rec_id:
                index[rec_id] = record
    return index


def atomic_write_jsonl(records: list[dict]) -> int:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JSONL_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp, JSONL_PATH)
    return len(records)


def materialize_json(records: list[dict]) -> None:
    """物化 JSON 数组（兼容 01 脚本 iter_json_array 流式读取）。"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JSON_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write("[")
        for i, record in enumerate(records):
            if i > 0:
                f.write(",")
            f.write(json.dumps(record, ensure_ascii=False))
        f.write("]")
    os.replace(tmp, JSON_PATH)


def sync_once(
    host: str,
    public_key: str,
    secret_key: str,
    path_prefix: str = "",
    force_full: bool = False,
    days: int | None = None,
    annotation_batch_size: int = 300,
) -> dict:
    """执行一轮同步。异常时 cursor 不更新，consecutive_failures += 1 后抛出。"""
    try:
        return _sync_once_inner(
            host, public_key, secret_key, path_prefix, force_full, days, annotation_batch_size
        )
    except Exception as exc:
        cursor = read_cursor()
        cursor["last_sync_at"] = _now_iso()
        cursor["consecutive_failures"] = cursor.get("consecutive_failures", 0) + 1
        cursor["last_error"] = str(exc)
        write_cursor(cursor)
        raise


def _sync_once_inner(
    host: str,
    public_key: str,
    secret_key: str,
    path_prefix: str,
    force_full: bool,
    days: int | None,
    annotation_batch_size: int,
) -> dict:
    # 1. 准备 scripts
    ensure_scripts_available()

    # 2. 客户端 + 连接测试
    client = LangfuseClient(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path_prefix=path_prefix,
    )
    test = client.test_connection()
    print(f"[connect] {test}")
    if test["status"] != "ok":
        raise RuntimeError(f"Langfuse connection failed: {test.get('error')}")

    # 3. 确定拉取起点
    cursor = read_cursor()
    now = datetime.now(timezone.utc)
    if force_full or not cursor.get("last_updated_at"):
        if force_full:
            print("[sync] --force-full: 全量重建")
        else:
            print("[sync] 无 cursor → backfill 模式")
        backfill_days = days if days is not None else BACKFILL_DAYS
        from_updated_at = None
        from_time = now - timedelta(days=backfill_days)
        print(f"[sync] backfill fromTimestamp = {from_time.isoformat()} ({backfill_days}d)")
    else:
        from_updated_at = datetime.fromisoformat(cursor["last_updated_at"])
        from_time = None
        print(f"[sync] 增量 fromUpdatedAt = {cursor['last_updated_at']}")

    # 4. 拉取（增量 upsert）
    existing = {} if force_full else load_existing_index()
    print(f"[sync] existing records: {len(existing)}")
    fetched: dict = {}
    for item in client.fetch_observations(
        from_time=from_time,
        from_updated_at=from_updated_at,
    ):
        rec_id = item.get("id") or item.get("traceId")
        if rec_id:
            fetched[rec_id] = item

    print(f"[sync] fetched new/updated: {len(fetched)}")
    if force_full:
        records = list(fetched.values())
        changed = len(records)
    else:
        merged = dict(existing)
        changed = 0
        for rec_id, record in fetched.items():
            prev = merged.get(rec_id)
            if prev is None:
                changed += 1
            elif record.get("updatedAt") != prev.get("updatedAt"):
                changed += 1
            merged[rec_id] = record
        records = list(merged.values())

    # 5. 原子写 jsonl + 物化 json
    n = atomic_write_jsonl(records)
    materialize_json(records)
    print(f"[sync] materialized {n} records -> {JSONL_PATH}")

    # 无实际新增/更新：只刷新 last_sync_at，跳过 pipeline 空转
    if changed == 0 and not force_full:
        print("[sync] no new/updated records. Skipping pipeline.")
        cursor = read_cursor()
        cursor["last_sync_at"] = _now_iso()
        cursor["total_records"] = n
        cursor["consecutive_failures"] = 0
        cursor.pop("last_error", None)
        write_cursor(cursor)
        return {"status": "ok", "new_records": 0, "total_records": n, "pipeline": "skipped"}

    if n == 0:
        print("[warn] No records. Skipping pipeline.")
        cursor = read_cursor()
        cursor["last_sync_at"] = _now_iso()
        cursor["total_records"] = 0
        cursor["consecutive_failures"] = 0
        write_cursor(cursor)
        return {"status": "ok", "new_records": 0, "total_records": 0, "pipeline": "skipped"}

    # 6. 跑 01/02/03（生成临时 config 指向物化目录）
    write_temp_config(annotation_batch_size)
    run_pipeline_scripts()

    # 7. 拷贝产出
    copied = copy_outputs_to_target()
    print(f"[sync] copied {copied} files -> {TARGET_OUTPUTS_DIR}")

    # 8. 最后更新 cursor（水位 = max 拉到的 updatedAt）
    max_updated = None
    for rec in records:
        upd = rec.get("updatedAt")
        if upd and (max_updated is None or upd > max_updated):
            max_updated = upd

    cursor = read_cursor()
    cursor["last_updated_at"] = max_updated or cursor.get("last_updated_at")
    cursor["last_sync_at"] = _now_iso()
    cursor["total_records"] = n
    cursor["consecutive_failures"] = 0
    cursor.pop("last_error", None)
    write_cursor(cursor)

    print(f"[sync] cursor updated: {cursor}")
    return {
        "status": "ok",
        "new_records": len(fetched),
        "total_records": n,
        "pipeline": "run",
        "copied_files": copied,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Langfuse 增量同步器")
    parser.add_argument("--host", default=None)
    parser.add_argument("--public-key", default=None)
    parser.add_argument("--secret-key", default=None)
    parser.add_argument("--path-prefix", default=None)
    parser.add_argument("--force-full", action="store_true", help="忽略 cursor 全量重建")
    parser.add_argument("--days", type=int, default=None, help="backfill 天数（默认 90）")
    parser.add_argument("--batch-size", type=int, default=None)
    args = parser.parse_args()

    env = load_env_file(PROJECT_ROOT / ".env")
    host = args.host or env.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_HOST", "")
    public_key = (
        args.public_key
        or env.get("LANGFUSE_PUBLIC_KEY")
        or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    )
    secret_key = (
        args.secret_key
        or env.get("LANGFUSE_SECRET_KEY")
        or os.environ.get("LANGFUSE_SECRET_KEY", "")
    )
    path_prefix = (
        args.path_prefix
        if args.path_prefix is not None
        else env.get("LANGFUSE_API_PATH_PREFIX", "")
    )
    batch_size = int(
        args.batch_size
        if args.batch_size is not None
        else env.get("LANGFUSE_ANNOTATION_BATCH_SIZE", "300")
    )

    if not all([host, public_key, secret_key]):
        print(
            "Missing Langfuse config. Set in .env or pass as args.\n"
            "  LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    result = sync_once(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path_prefix=path_prefix,
        force_full=args.force_full,
        days=args.days,
        annotation_batch_size=batch_size,
    )
    print("\n=== Done ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()