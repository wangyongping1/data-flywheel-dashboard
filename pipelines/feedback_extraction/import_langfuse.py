from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PIPELINE_OUTPUT_FILES = [
    "annotation_batch.csv",
    "profile_stats.json",
    "trace_summary.csv",
    "trace_summary.jsonl",
    "training_dataset.csv",
    "training_dataset.jsonl",
]

EXPORT_FILES = [
    "observations.json",
    "observations_preview.json",
    "observations_summary.csv",
]


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _write_manifest(path: Path, copied_files: int) -> dict:
    manifest = {
        "status": "ok",
        "source": "user-provided Langfuse import source",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "copied_files": copied_files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def import_langfuse(source: Path, import_dir: Path, output_dir: Path) -> dict:
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Langfuse source does not exist: {source}")

    export_source = source / "langfuse-export-artifacts"
    pipeline_source = source / "langfuse-dataset-pipeline" / "outputs"
    if not export_source.exists() and not pipeline_source.exists():
        raise FileNotFoundError(
            "Langfuse source must contain langfuse-export-artifacts or "
            "langfuse-dataset-pipeline/outputs"
        )

    copied = 0
    for name in EXPORT_FILES:
        if _copy_file(export_source / name, import_dir / "langfuse-export-artifacts" / name):
            copied += 1

    scripts_source = source / "langfuse-dataset-pipeline" / "scripts"
    scripts_target = import_dir / "langfuse-dataset-pipeline" / "scripts"
    if scripts_source.exists():
        if scripts_target.exists():
            shutil.rmtree(scripts_target)
        shutil.copytree(scripts_source, scripts_target, ignore=shutil.ignore_patterns("__pycache__"))
        copied += len([p for p in scripts_target.rglob("*") if p.is_file()])

    for name in PIPELINE_OUTPUT_FILES:
        src = pipeline_source / name
        if _copy_file(src, import_dir / "langfuse-dataset-pipeline" / "outputs" / name):
            copied += 1
        if _copy_file(src, output_dir / name):
            copied += 1

    return _write_manifest(import_dir / "import_manifest.json", copied)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Langfuse data into Data Flywheel.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--import-dir", default=Path("data/imports/langfuse"), type=Path)
    parser.add_argument("--output-dir", default=Path("data/outputs/langfuse_pipeline"), type=Path)
    args = parser.parse_args()

    result = import_langfuse(args.source, args.import_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
