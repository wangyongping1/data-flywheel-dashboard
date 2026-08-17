import csv

from common_config import load_config, pipeline_output_path

TRACE_SUMMARY = pipeline_output_path("trace_summary_csv")
ANNOTATION_BATCH = pipeline_output_path("annotation_batch_csv")


def score_candidate(row):
    score = 0
    if int(row.get("generationCount") or 0) > 0:
        score += 5
    if row.get("firstInput"):
        score += 3
    if row.get("finalOutput"):
        score += 3
    if int(row.get("errorCount") or 0) > 0:
        score += 2
    tokens = int(row.get("totalTokens") or 0)
    if tokens > 0:
        score += min(tokens // 1000, 5)
    return score


def main(limit=None):
    if limit is None:
        limit = int(load_config()["dataset_pipeline"]["annotation_batch_size"])

    if not TRACE_SUMMARY.exists():
        raise RuntimeError("trace_summary.csv not found. Run 01_build_trace_summary.py first.")

    with TRACE_SUMMARY.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    rows.sort(key=score_candidate, reverse=True)
    selected = rows[:limit]

    annotation_fields = [
        "include_in_dataset",
        "correctness",
        "helpfulness",
        "hallucination",
        "safety",
        "expected_output",
        "comment",
    ]

    fieldnames = [
        "traceId",
        "traceName",
        "sessionId",
        "userId",
        "environment",
        "firstStartTime",
        "lastEndTime",
        "observationCount",
        "generationCount",
        "models",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "totalCost",
        "errorCount",
        "firstInput",
        "finalOutput",
        *annotation_fields,
    ]

    with ANNOTATION_BATCH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected:
            output = {field: row.get(field, "") for field in fieldnames}
            for field in annotation_fields:
                output[field] = ""
            writer.writerow(output)

    print(f"Selected traces for annotation: {len(selected)}")
    print(f"Saved: {ANNOTATION_BATCH}")


if __name__ == "__main__":
    main()
