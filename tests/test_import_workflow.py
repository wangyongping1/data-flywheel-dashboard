import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class ImportWorkflowTests(unittest.TestCase):
    def test_import_langfuse_copies_inputs_and_publishes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            export_dir = source / "langfuse-export-artifacts"
            pipeline_outputs = source / "langfuse-dataset-pipeline" / "outputs"
            export_dir.mkdir(parents=True)
            pipeline_outputs.mkdir(parents=True)
            (export_dir / "observations.json").write_text('{"ok": true}\n', encoding="utf-8")
            (export_dir / "observations_summary.csv").write_text("id,total\n1,2\n", encoding="utf-8")
            (pipeline_outputs / "profile_stats.json").write_text('{"traceCount": 1}\n', encoding="utf-8")
            (pipeline_outputs / "trace_summary.csv").write_text("traceId,totalTokens\nabc,42\n", encoding="utf-8")
            (pipeline_outputs / "annotation_batch.csv").write_text("traceId,include_in_dataset\nabc,yes\n", encoding="utf-8")
            (pipeline_outputs / "training_dataset.jsonl").write_text('{"traceId":"abc"}\n', encoding="utf-8")

            from pipelines.feedback_extraction.import_langfuse import import_langfuse

            result = import_langfuse(
                source=source,
                import_dir=root / "data" / "imports" / "langfuse",
                output_dir=root / "data" / "outputs" / "langfuse_pipeline",
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue((root / "data" / "imports" / "langfuse" / "langfuse-export-artifacts" / "observations.json").exists())
            self.assertTrue((root / "data" / "outputs" / "langfuse_pipeline" / "trace_summary.csv").exists())
            manifest = json.loads((root / "data" / "imports" / "langfuse" / "import_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"], "user-provided Langfuse import source")
            self.assertGreaterEqual(manifest["copied_files"], 6)

    def test_import_langfuse_rejects_missing_source(self):
        from pipelines.feedback_extraction.import_langfuse import import_langfuse

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                import_langfuse(
                    source=root / "missing",
                    import_dir=root / "imports",
                    output_dir=root / "outputs",
                )

    def test_import_evaluation_copies_results_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "batch-runner"
            result_dir = source / "results" / "2026-01-01_00-00-00"
            result_dir.mkdir(parents=True)
            (result_dir / "report.json").write_text('{"task__agent__model":{"accuracy":67.1}}\n', encoding="utf-8")

            from pipelines.evaluation.import_evaluation import import_evaluation

            result = import_evaluation(
                source=source,
                import_dir=root / "data" / "imports" / "evaluation",
                output_dir=root / "data" / "outputs" / "evaluation",
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue((root / "data" / "imports" / "evaluation" / "results" / "2026-01-01_00-00-00" / "report.json").exists())
            self.assertTrue((root / "data" / "outputs" / "evaluation" / "results" / "2026-01-01_00-00-00" / "report.json").exists())
            manifest = json.loads((root / "data" / "imports" / "evaluation" / "import_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"], "user-provided evaluation import source")
            self.assertEqual(manifest["copied_files"], 1)

    def test_backend_config_prefers_project_local_import_paths(self):
        old_env = {key: os.environ.get(key) for key in ["FLYWHEEL_DATA_DIR", "LANGFUSE_EXPORT_DIR", "LANGFUSE_PIPELINE_DIR", "EVAL_RESULTS_DIR", "TRAINING_DIR"]}
        for key in old_env:
            os.environ.pop(key, None)
        try:
            import backend.config as config
            config = importlib.reload(config)

            root = Path(__file__).resolve().parents[1]
            self.assertEqual(config.LANGFUSE_EXPORT_DIR, root / "data" / "imports" / "langfuse" / "langfuse-export-artifacts")
            self.assertEqual(config.LANGFUSE_PIPELINE_DIR, root / "data" / "outputs" / "langfuse_pipeline")
            self.assertEqual(config.EVAL_RESULTS_DIR, root / "data" / "outputs" / "evaluation" / "results")
            self.assertEqual(config.ANNOTATION_CSV, root / "data" / "outputs" / "langfuse_pipeline" / "annotation_batch.csv")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
