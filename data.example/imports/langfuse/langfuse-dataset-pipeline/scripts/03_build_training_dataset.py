import csv
import json

from common_config import pipeline_output_path

ANNOTATION_BATCH = pipeline_output_path("annotation_batch_csv")
DATASET_JSONL = pipeline_output_path("training_dataset_jsonl")
DATASET_CSV = pipeline_output_path("training_dataset_csv")


def should_include(row):
    return (row.get("include_in_dataset") or "").strip().lower() in {"yes", "y", "true", "1"}


def build_example(row):
    expected_output = (row.get("expected_output") or "").strip()
    target_output = expected_output or row.get("finalOutput", "")
    return {
        "traceId": row.get("traceId", ""),
        "input": row.get("firstInput", ""),
        "output": target_output,
        "source_output": row.get("finalOutput", ""),
        "labels": {
            "correctness": row.get("correctness", ""),
            "helpfulness": row.get("helpfulness", ""),
            "hallucination": row.get("hallucination", ""),
            "safety": row.get("safety", ""),
        },
        "metadata": {
            "traceName": row.get("traceName", ""),
            "sessionId": row.get("sessionId", ""),
            "userId": row.get("userId", ""),
            "environment": row.get("environment", ""),
            "models": row.get("models", ""),
            "totalTokens": row.get("totalTokens", ""),
            "comment": row.get("comment", ""),
        },
    }


def main():
    if not ANNOTATION_BATCH.exists():
        raise RuntimeError("annotation_batch.csv not found. Run 02_build_annotation_batch.py first.")

    with ANNOTATION_BATCH.open("r", encoding="utf-8-sig", newline="") as file:
        rows = [row for row in csv.DictReader(file) if should_include(row)]

    examples = [build_example(row) for row in rows]

    with DATASET_JSONL.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False) + "\n")

    fieldnames = [
        "traceId",
        "input",
        "output",
        "source_output",
        "correctness",
        "helpfulness",
        "hallucination",
        "safety",
        "traceName",
        "sessionId",
        "userId",
        "environment",
        "models",
        "totalTokens",
        "comment",
    ]

    with DATASET_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for example in examples:
            writer.writerow(
                {
                    "traceId": example["traceId"],
                    "input": example["input"],
                    "output": example["output"],
                    "source_output": example["source_output"],
                    "correctness": example["labels"]["correctness"],
                    "helpfulness": example["labels"]["helpfulness"],
                    "hallucination": example["labels"]["hallucination"],
                    "safety": example["labels"]["safety"],
                    "traceName": example["metadata"]["traceName"],
                    "sessionId": example["metadata"]["sessionId"],
                    "userId": example["metadata"]["userId"],
                    "environment": example["metadata"]["environment"],
                    "models": example["metadata"]["models"],
                    "totalTokens": example["metadata"]["totalTokens"],
                    "comment": example["metadata"]["comment"],
                }
            )

    print(f"Approved examples: {len(examples)}")
    print(f"Saved: {DATASET_JSONL}")
    print(f"Saved: {DATASET_CSV}")


if __name__ == "__main__":
    main()
