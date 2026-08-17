from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _copy_results(source_results: Path, target_results: Path) -> int:
    if target_results.exists():
        shutil.rmtree(target_results)
    shutil.copytree(
        source_results,
        target_results,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.out.log", "*.err.log"),
    )
    return len([p for p in target_results.rglob("*") if p.is_file()])


def _write_manifest(path: Path, copied_files: int, published_files: int) -> dict:
    manifest = {
        "status": "ok",
        "source": "user-provided evaluation import source",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "copied_files": copied_files,
        "published_files": published_files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def import_evaluation(source: Path, import_dir: Path, output_dir: Path) -> dict:
    source = Path(source)
    results_source = source / "results"
    if not results_source.exists():
        raise FileNotFoundError(f"Evaluation source must contain results/: {source}")

    copied_import = _copy_results(results_source, import_dir / "results")
    copied_output = _copy_results(results_source, output_dir / "results")
    return _write_manifest(import_dir / "import_manifest.json", copied_import, copied_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import evaluation results into Data Flywheel.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--import-dir", default=Path("data/imports/evaluation"), type=Path)
    parser.add_argument("--output-dir", default=Path("data/outputs/evaluation"), type=Path)
    args = parser.parse_args()

    result = import_evaluation(args.source, args.import_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
