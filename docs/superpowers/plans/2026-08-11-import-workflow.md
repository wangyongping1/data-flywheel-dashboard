# Import Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Data Flywheel own an importable data layout so the demo can run from project-local Langfuse and evaluation data, while keeping the original referenced folders read-only.

**Architecture:** Add business-named `data/imports`, `data/outputs`, and `pipelines` directories. Import scripts copy read-only source data into project-owned import folders, then publish the normalized files the backend already expects into `data/outputs`. Backend config prefers project-local outputs and falls back to external env paths only when local data has not been imported.

**Tech Stack:** Python standard library, FastAPI backend config, existing React frontend reads unchanged API contracts.

## Global Constraints

- Do not depend on machine-specific external Langfuse or evaluation directories at runtime.
- Import source paths must be passed explicitly to importer commands.
- Prefer project-local imported data after this change.
- Preserve project-local env vars `FLYWHEEL_DATA_DIR`, `LANGFUSE_EXPORT_DIR`, `LANGFUSE_PIPELINE_DIR`, `EVAL_RESULTS_DIR`, and `TRAINING_DIR`.
- Do not copy caches, `node_modules`, `__pycache__`, temporary logs, or build artifacts.

---

### Task 1: Langfuse Importer

**Files:**
- Create: `pipelines/feedback_extraction/import_langfuse.py`
- Test: `tests/test_import_workflow.py`

**Interfaces:**
- Produces: `import_langfuse(source: Path, import_dir: Path, output_dir: Path) -> dict`
- Produces files under `data/imports/langfuse` and `data/outputs/langfuse_pipeline`.

- [ ] Write failing tests for copying export artifacts, publishing pipeline outputs, writing manifest, and rejecting missing source folders.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify importer tests fail because the module does not exist.
- [ ] Implement `import_langfuse`.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify importer tests pass.

### Task 2: Evaluation Importer

**Files:**
- Create: `pipelines/evaluation/import_evaluation.py`
- Test: `tests/test_import_workflow.py`

**Interfaces:**
- Produces: `import_evaluation(source: Path, import_dir: Path, output_dir: Path) -> dict`
- Produces files under `data/imports/evaluation/results` and `data/outputs/evaluation/results`.

- [ ] Write failing tests for copying `results` and writing manifest.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify evaluation importer tests fail because the module does not exist.
- [ ] Implement `import_evaluation`.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify all importer tests pass.

### Task 3: Backend Config Defaults

**Files:**
- Modify: `backend/config.py`
- Test: `tests/test_import_workflow.py`

**Interfaces:**
- Produces config constants that prefer project-local imported data:
  - `LANGFUSE_EXPORT_DIR`
  - `LANGFUSE_PIPELINE_DIR`
  - `ANNOTATION_CSV`
  - `TRAINING_DATASET_JSONL`
  - `EVAL_RESULTS_DIR`

- [ ] Write failing tests that import `backend.config` and verify default paths point at `data/imports` and `data/outputs`.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify config path tests fail with current external defaults.
- [ ] Update `backend/config.py` with project-local defaults and env fallback.
- [ ] Run `python -m unittest tests.test_import_workflow` and verify config tests pass.

### Task 4: Seed Current Data and Docs

**Files:**
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Create project-owned data under:
  - `data/imports/langfuse`
  - `data/outputs/langfuse_pipeline`
  - `data/imports/evaluation`
  - `data/outputs/evaluation`

**Interfaces:**
- Uses importer CLIs:
  - `python pipelines/feedback_extraction/import_langfuse.py --source "<langfuse-export-root>"`
  - `python pipelines/evaluation/import_evaluation.py --source "<evaluation-runner-root>"`

- [ ] Run both importers against the current read-only source folders.
- [ ] Verify manifests were written.
- [ ] Verify backend readers return summary data from project-local paths.
- [ ] Update README and HANDOFF with the import workflow and future automatic import path.
- [ ] Run `python -m py_compile` for backend and pipeline files.
- [ ] Run `npm run build` in `frontend`.
