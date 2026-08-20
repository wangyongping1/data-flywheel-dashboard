import json
from datetime import datetime
from pathlib import Path

from config import TRAINING_DIR


class TrainingReader:
    def __init__(self, runs_dir: Path = None):
        self.runs_dir = runs_dir or (TRAINING_DIR / "runs")

    def get_runs_index(self) -> list[dict]:
        index_path = self.runs_dir / "index.json"
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text(encoding="utf-8"))

    def get_total_runs(self) -> int:
        return len(self.get_runs_index())

    def get_completed_runs(self) -> list[dict]:
        return [r for r in self.get_runs_index() if r.get("status") == "completed"]

    def get_last_run_time(self) -> str | None:
        runs = self.get_runs_index()
        if runs:
            return runs[0].get("timestamp")
        return None

    def get_latest_run(self) -> dict | None:
        runs = self.get_runs_index()
        if runs:
            return runs[0]
        return None

    def get_kpi(self) -> dict:
        runs = self.get_runs_index()
        completed = self.get_completed_runs()
        latest = self.get_latest_run()

        return {
            "total_runs": len(runs),
            "completed_runs": len(completed),
            "status": "active" if len(completed) > 0 else ("pending" if len(runs) > 0 else "not_connected"),
            "last_run_at": self.get_last_run_time(),
            "latest_run": {
                "run_id": latest.get("run_id"),
                "model": latest.get("model"),
                "status": latest.get("status"),
                "metrics": latest.get("metrics", {}),
            } if latest else None,
            "runs_history": runs[:10],
        }
