import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config():
    local_path = REPO_ROOT / "config.local.json"
    example_path = REPO_ROOT / "config.example.json"
    config_path = local_path if local_path.exists() else example_path

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    return config


def repo_path(value):
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def export_path(filename_key):
    config = load_config()
    export_config = config["export"]
    return repo_path(export_config["output_dir"]) / export_config[filename_key]


def pipeline_output_path(filename_key):
    config = load_config()
    pipeline_config = config["dataset_pipeline"]
    return repo_path(pipeline_config["output_dir"]) / pipeline_config[filename_key]


def pipeline_output_dir():
    config = load_config()
    return repo_path(config["dataset_pipeline"]["output_dir"])
