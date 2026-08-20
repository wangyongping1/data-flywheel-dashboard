import json
from datetime import datetime
from pathlib import Path

from config import EVAL_RESULTS_DIR


class EvalReader:
    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or EVAL_RESULTS_DIR

    def get_all_sessions(self) -> list[dict]:
        sessions = []
        if not self.results_dir.exists():
            return sessions

        for session_dir in sorted(self.results_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            report_path = session_dir / "report.json"
            if not report_path.exists():
                continue

            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            session_data = {
                "session_id": session_dir.name,
                "timestamp": self._parse_session_time(session_dir.name),
                "results": [],
            }

            for key, metrics in report.items():
                parts = key.split("__")
                task = parts[0] if len(parts) >= 1 else "unknown"
                agent = parts[1] if len(parts) >= 2 else "unknown"
                model_full = parts[2] if len(parts) >= 3 else "unknown"
                provider = model_full.split("/")[0] if "/" in model_full else "unknown"
                model = model_full.split("/")[-1] if "/" in model_full else model_full

                session_data["results"].append({
                    "task": task,
                    "agent": agent,
                    "provider": provider,
                    "model": model,
                    "accuracy": metrics.get("accuracy", 0.0),
                    "ci": metrics.get("ci", 0.0),
                    "passed": metrics.get("passed", 0),
                    "failed": metrics.get("failed", 0),
                    "total": metrics.get("total", 0),
                    "errors": metrics.get("errors", 0),
                    "infrastructure_errors": metrics.get("infrastructure_errors", 0),
                    "avg_time_sec": metrics.get("avg_time_sec", 0.0),
                    "avg_cost": metrics.get("avg_cost", 0.0),
                    "avg_input_tokens": metrics.get("avg_input_tokens", 0.0),
                    "avg_output_tokens": metrics.get("avg_output_tokens", 0.0),
                })

            sessions.append(session_data)

        return sessions

    def get_total_sessions(self) -> int:
        return len(self.get_all_sessions())

    def get_total_trials(self) -> int:
        total = 0
        for session in self.get_all_sessions():
            for r in session["results"]:
                total += r["total"]
        return total

    def get_best_result(self) -> dict | None:
        best = None
        for session in self.get_all_sessions():
            for r in session["results"]:
                if r["total"] == 0:
                    continue
                if best is None or r["accuracy"] > best["accuracy"]:
                    best = r
        return best

    def get_last_eval_time(self) -> str | None:
        sessions = self.get_all_sessions()
        if sessions:
            return sessions[0]["timestamp"]
        return None

    def get_leaderboard(self) -> list[dict]:
        scores = {}
        for session in self.get_all_sessions():
            for r in session["results"]:
                if r["total"] == 0:
                    continue
                key = f"{r['agent']}__{r['model']}"
                if key not in scores or r["accuracy"] > scores[key]["accuracy"]:
                    scores[key] = r

        leaderboard = sorted(scores.values(), key=lambda x: x["accuracy"], reverse=True)
        for i, entry in enumerate(leaderboard, 1):
            entry["rank"] = i
        return leaderboard

    def get_kpi(self) -> dict:
        best = self.get_best_result()
        return {
            "total_sessions": self.get_total_sessions(),
            "total_trials": self.get_total_trials(),
            "best_accuracy": best["accuracy"] if best else 0.0,
            "best_config": {
                "agent": best["agent"],
                "model": best["model"],
                "task": best["task"],
            } if best else None,
            "last_eval_at": self.get_last_eval_time(),
        }

    @staticmethod
    def _parse_session_time(session_name: str) -> str:
        try:
            dt = datetime.strptime(session_name, "%Y-%m-%d_%H-%M-%S")
            return dt.isoformat()
        except ValueError:
            return session_name
