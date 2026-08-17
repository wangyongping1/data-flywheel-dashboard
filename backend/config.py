import os
from pathlib import Path

def _default_flywheel_root() -> Path:
    here = Path(__file__).resolve()
    if here.parent.name == "backend":
        return here.parents[1]
    return here.parent


FLYWHEEL_ROOT = Path(os.getenv("FLYWHEEL_ROOT", str(_default_flywheel_root())))
DATA_DIR = Path(os.getenv("FLYWHEEL_DATA_DIR", str(FLYWHEEL_ROOT / "data")))
DATA_IMPORTS_DIR = DATA_DIR / "imports"
DATA_OUTPUTS_DIR = DATA_DIR / "outputs"

PROJECT_LANGFUSE_IMPORT_DIR = DATA_IMPORTS_DIR / "langfuse"
PROJECT_LANGFUSE_EXPORT_DIR = PROJECT_LANGFUSE_IMPORT_DIR / "langfuse-export-artifacts"
PROJECT_LANGFUSE_PIPELINE_DIR = DATA_OUTPUTS_DIR / "langfuse_pipeline"

PROJECT_EVAL_OUTPUT_DIR = DATA_OUTPUTS_DIR / "evaluation"

TRAINING_DIR = Path(os.getenv("TRAINING_DIR", str(FLYWHEEL_ROOT / "training")))

LANGFUSE_EXPORT_DIR = Path(os.getenv("LANGFUSE_EXPORT_DIR", str(PROJECT_LANGFUSE_EXPORT_DIR)))
LANGFUSE_PIPELINE_DIR = Path(os.getenv("LANGFUSE_PIPELINE_DIR", str(PROJECT_LANGFUSE_PIPELINE_DIR)))
ANNOTATION_CSV = LANGFUSE_PIPELINE_DIR / "annotation_batch.csv"
TRAINING_DATASET_JSONL = LANGFUSE_PIPELINE_DIR / "training_dataset.jsonl"

EVAL_RESULTS_DIR = Path(os.getenv("EVAL_RESULTS_DIR", str(PROJECT_EVAL_OUTPUT_DIR / "results")))
TRAINING_RUNS_DIR = TRAINING_DIR / "runs"
