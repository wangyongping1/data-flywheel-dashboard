"""从 Langfuse 直连拉取数据并产出训练集（一键闭环）。

流程：
1. 用 LangfuseClient 调 /api/public/observations 拉数据
2. 保存为 observations.json（兼容 01 脚本的 iter_json_array 流式读取）
3. 生成临时 config.local.json，让 01/02/03 脚本读项目内路径
4. subprocess 依次跑 01/02/03 脚本，产出 trace_summary.csv / annotation_batch.csv / training_dataset.jsonl
5. 拷贝产出到 data/outputs/langfuse_pipeline/（与 import_langfuse.py 一致的标准目录）
6. 写 import_manifest.json

用法：
    python pipelines/feedback_extraction/fetch_and_import.py

配置来自 .env：
    LANGFUSE_HOST=https://agentos.hqzyai.com
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx
    LANGFUSE_SECRET_KEY=sk-lf-xxx
    LANGFUSE_API_PATH_PREFIX=           # 空 = /api/public；若 API 有代理前缀填 /ai-observability
    LANGFUSE_FETCH_DAYS=30              # 时间窗口（天）
    LANGFUSE_ANNOTATION_BATCH_SIZE=300  # 02 脚本候选样本数
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langfuse_client import LangfuseClient, save_observations_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# data 根目录：支持 FLYWHEEL_DATA_DIR 覆盖（backend 容器内为 /app/project_data）
DATA_DIR = Path(os.getenv("FLYWHEEL_DATA_DIR") or (PROJECT_ROOT / "data"))
PIPELINE_DIR = DATA_DIR / "imports" / "langfuse" / "langfuse-dataset-pipeline"
SCRIPTS_DIR = PIPELINE_DIR / "scripts"
# 物化目录：与 backend/config.py 的 LANGFUSE_EXPORT_DIR 对齐（data/imports/langfuse/langfuse-export-artifacts）
EXPORT_DIR = DATA_DIR / "imports" / "langfuse" / "langfuse-export-artifacts"
OUTPUTS_DIR = PIPELINE_DIR / "outputs"
TARGET_OUTPUTS_DIR = DATA_DIR / "outputs" / "langfuse_pipeline"
IMPORT_ROOT = DATA_DIR / "imports" / "langfuse"

PIPELINE_OUTPUT_FILES = [
    "trace_summary.csv",
    "trace_summary.jsonl",
    "annotation_batch.csv",
    "training_dataset.csv",
    "training_dataset.jsonl",
    "profile_stats.json",
]

PIPELINE_SCRIPTS = [
    "01_build_trace_summary.py",
    "02_build_annotation_batch.py",
    "03_build_training_dataset.py",
]


def load_env_file(env_path: Path) -> dict:
    """轻量 .env 读取，不依赖 python-dotenv。"""
    values: dict = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        value = raw.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def ensure_scripts_available() -> None:
    """scripts 目录不存在时，从 data.example 拷贝演示副本。"""
    if SCRIPTS_DIR.exists() and (SCRIPTS_DIR / "01_build_trace_summary.py").exists():
        return
    example_scripts = (
        PROJECT_ROOT / "data.example" / "imports" / "langfuse" / "langfuse-dataset-pipeline" / "scripts"
    )
    if not example_scripts.exists():
        raise FileNotFoundError(
            f"Pipeline scripts not found.\n"
            f"Expected at: {SCRIPTS_DIR}\n"
            f"Fallback at: {example_scripts}\n"
            f"Run import_langfuse.py first, or copy scripts manually."
        )
    SCRIPTS_DIR.parent.mkdir(parents=True, exist_ok=True)
    if SCRIPTS_DIR.exists():
        shutil.rmtree(SCRIPTS_DIR)
    shutil.copytree(
        example_scripts, SCRIPTS_DIR, ignore=shutil.ignore_patterns("__pycache__")
    )
    print(f"[setup] Copied pipeline scripts from data.example -> {SCRIPTS_DIR}")


def write_temp_config(annotation_batch_size: int) -> Path:
    """生成临时 config.local.json，让 01/02/03 脚本读项目内路径。

    common_config.py 用 Path(__file__).resolve().parents[2] 作为 REPO_ROOT，
    即 scripts 目录往上 3 级 = data/imports/langfuse。config.local.json 放在这里。
    """
    config = {
        "export": {
            "output_dir": str(EXPORT_DIR),
            "full_json": "observations.json",
            "summary_csv": "observations_summary.csv",
        },
        "dataset_pipeline": {
            "output_dir": str(OUTPUTS_DIR),
            "trace_summary_csv": "trace_summary.csv",
            "trace_summary_jsonl": "trace_summary.jsonl",
            "profile_stats_json": "profile_stats.json",
            "annotation_batch_csv": "annotation_batch.csv",
            "annotation_batch_size": annotation_batch_size,
            "training_dataset_jsonl": "training_dataset.jsonl",
            "training_dataset_csv": "training_dataset.csv",
        },
    }
    scripts_repo_root = SCRIPTS_DIR.parents[1]
    scripts_repo_root.mkdir(parents=True, exist_ok=True)
    config_path = scripts_repo_root / "config.local.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config_path


def run_pipeline_scripts() -> None:
    """subprocess 依次跑 01/02/03 脚本。"""
    for script_name in PIPELINE_SCRIPTS:
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"Pipeline script missing: {script_path}")
        print(f"\n>>> Running {script_name} ...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SCRIPTS_DIR),
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{script_name} failed with exit code {result.returncode}"
            )


def copy_outputs_to_target() -> int:
    """把产出拷贝到 data/outputs/langfuse_pipeline/（后端默认读取目录）。"""
    TARGET_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in PIPELINE_OUTPUT_FILES:
        src = OUTPUTS_DIR / name
        if src.exists():
            shutil.copy2(src, TARGET_OUTPUTS_DIR / name)
            copied += 1
    return copied


def write_manifest(observation_count: int, copied_files: int) -> dict:
    manifest = {
        "status": "ok",
        "source": "langfuse-direct-api",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "observation_count": observation_count,
        "copied_files": copied_files,
        "outputs_dir": str(TARGET_OUTPUTS_DIR),
    }
    IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = IMPORT_ROOT / "import_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def fetch_and_import(
    host: str,
    public_key: str,
    secret_key: str,
    path_prefix: str = "",
    from_days: int = 30,
    annotation_batch_size: int = 300,
) -> dict:
    """一键拉取 + 处理 + 拷贝。"""
    # 1. 准备 scripts
    ensure_scripts_available()

    # 2. 拉数据
    client = LangfuseClient(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path_prefix=path_prefix,
    )

    test = client.test_connection()
    print(f"[connect] {test}")
    if test["status"] != "ok":
        raise RuntimeError(
            f"Langfuse connection failed: {test.get('error')}\n"
            f"Check host/keys/path_prefix. api_base={test.get('api_base')}"
        )

    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=from_days)
    print(
        f"\n[fetch] observations from {from_time.isoformat()} to {to_time.isoformat()} ..."
    )

    # 3. 保存 observations.json
    observations_path = EXPORT_DIR / "observations.json"
    observation_count = save_observations_json(
        observations_path, client.fetch_observations(from_time, to_time)
    )
    print(f"[fetch] Saved {observation_count} observations -> {observations_path}")

    if observation_count == 0:
        print("[warn] No observations fetched. Skipping pipeline.")
        return write_manifest(0, 0)

    # 4. 生成临时 config
    config_path = write_temp_config(annotation_batch_size)
    print(f"[config] Wrote temp config -> {config_path}")

    # 5. 跑 01/02/03
    run_pipeline_scripts()

    # 6. 拷贝产出
    copied = copy_outputs_to_target()
    print(f"\n[copy] {copied} files -> {TARGET_OUTPUTS_DIR}")

    # 7. 写 manifest
    manifest = write_manifest(observation_count, copied)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch observations from Langfuse API and run the full pipeline."
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Langfuse host, e.g. https://agentos.hqzyai.com (overrides .env)",
    )
    parser.add_argument(
        "--public-key", default=None, help="Langfuse public key (overrides .env)"
    )
    parser.add_argument(
        "--secret-key", default=None, help="Langfuse secret key (overrides .env)"
    )
    parser.add_argument(
        "--path-prefix",
        default=None,
        help="API path prefix, e.g. /ai-observability. Empty = standard /api/public",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Time window in days (default 30)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Annotation batch size (default 300)",
    )
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
    from_days = int(
        args.days
        if args.days is not None
        else env.get("LANGFUSE_FETCH_DAYS", "30")
    )
    batch_size = int(
        args.batch_size
        if args.batch_size is not None
        else env.get("LANGFUSE_ANNOTATION_BATCH_SIZE", "300")
    )

    if not all([host, public_key, secret_key]):
        print(
            "Missing Langfuse config. Set in .env or pass as args:\n"
            "  LANGFUSE_HOST=https://agentos.hqzyai.com\n"
            "  LANGFUSE_PUBLIC_KEY=pk-lf-xxx\n"
            "  LANGFUSE_SECRET_KEY=sk-lf-xxx\n"
            "Optional: LANGFUSE_API_PATH_PREFIX, LANGFUSE_FETCH_DAYS, LANGFUSE_ANNOTATION_BATCH_SIZE",
            file=sys.stderr,
        )
        sys.exit(1)

    result = fetch_and_import(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path_prefix=path_prefix,
        from_days=from_days,
        annotation_batch_size=batch_size,
    )
    print("\n=== Done ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
