import csv
from datetime import datetime
from pathlib import Path

from config import LANGFUSE_PIPELINE_DIR

_APPROVED_VALUES = {"yes", "y", "true", "1"}
_REVIEWED_VALUES = {"yes", "y", "true", "1", "no", "n", "false", "0"}


class DatasetReader:
    def __init__(self, pipeline_dir: Path = None):
        self.pipeline_dir = pipeline_dir or LANGFUSE_PIPELINE_DIR

    def _read_csv(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def get_annotation_batch(self) -> list[dict]:
        return self._read_csv(self.pipeline_dir / "annotation_batch.csv")

    def get_training_dataset(self) -> list[dict]:
        jsonl_path = self.pipeline_dir / "training_dataset.jsonl"
        if not jsonl_path.exists():
            return []
        with jsonl_path.open("r", encoding="utf-8") as f:
            import json
            return [json.loads(line) for line in f if line.strip()]

    @staticmethod
    def _count_from_rows(rows: list[dict]) -> tuple[int, int, int]:
        """从已读 rows 一次性算出 (total, reviewed, approved)。"""
        reviewed = 0
        approved = 0
        for r in rows:
            val = (r.get("include_in_dataset") or "").strip().lower()
            if val in _REVIEWED_VALUES:
                reviewed += 1
            if val in _APPROVED_VALUES:
                approved += 1
        return len(rows), reviewed, approved

    def get_total_candidates(self) -> int:
        return len(self.get_annotation_batch())

    def get_reviewed_count(self) -> int:
        return self._count_from_rows(self.get_annotation_batch())[1]

    def get_approved_count(self) -> int:
        return self._count_from_rows(self.get_annotation_batch())[2]

    def get_review_progress(self) -> float:
        total, reviewed, _ = self._count_from_rows(self.get_annotation_batch())
        if total == 0:
            return 0.0
        return round(reviewed / total, 4)

    def get_last_annotation_time(self) -> str | None:
        csv_path = self.pipeline_dir / "annotation_batch.csv"
        if csv_path.exists():
            ts = csv_path.stat().st_mtime
            return datetime.fromtimestamp(ts).isoformat()
        return None

    def get_kpi(self) -> dict:
        # 读一次 CSV，一次性算完所有指标（P1 修复：原实现一次 get_kpi 读 4 遍 CSV）
        rows = self.get_annotation_batch()
        total, reviewed, approved = self._count_from_rows(rows)
        review_progress = round(reviewed / total, 4) if total > 0 else 0.0
        return {
            "total_candidates": total,
            "total_reviewed": reviewed,
            "total_approved": approved,
            "review_progress": review_progress,
            "last_annotation_at": self.get_last_annotation_time(),
        }
