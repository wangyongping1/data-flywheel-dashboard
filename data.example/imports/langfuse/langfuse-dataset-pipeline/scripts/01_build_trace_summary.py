import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from common_config import export_path, load_config, pipeline_output_dir, pipeline_output_path

SOURCE = export_path("full_json")
SUMMARY_SOURCE = export_path("summary_csv")
OUTPUT_DIR = pipeline_output_dir()


def compact(value, max_length=500):
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text[:max_length] + "..." if len(text) > max_length else text


def first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def usage_value(item, key):
    usage = item.get("usageDetails") or {}
    legacy = item.get("usage") or {}
    return usage.get(key) or legacy.get(key) or 0


def cost_value(item):
    costs = item.get("costDetails") or {}
    return costs.get("total") or item.get("calculatedTotalCost") or 0


def iter_json_array(path, chunk_size=1024 * 1024):
    decoder = json.JSONDecoder()
    buffer = ""
    position = 0
    started = False
    finished = False

    with path.open("r", encoding="utf-8") as file:
        while not finished:
            chunk = file.read(chunk_size)
            if chunk:
                buffer += chunk
            elif position >= len(buffer):
                break

            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1

                if not started:
                    if position >= len(buffer):
                        break
                    if buffer[position] != "[":
                        raise ValueError("Expected JSON array")
                    started = True
                    position += 1
                    continue

                while position < len(buffer) and buffer[position].isspace():
                    position += 1

                if position < len(buffer) and buffer[position] == ",":
                    position += 1
                    continue

                if position < len(buffer) and buffer[position] == "]":
                    finished = True
                    break

                try:
                    item, end = decoder.raw_decode(buffer, position)
                except json.JSONDecodeError:
                    if not chunk:
                        raise
                    break

                yield item
                position = end

                if position > chunk_size:
                    buffer = buffer[position:]
                    position = 0


def load_summary_rows():
    with SUMMARY_SOURCE.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def build_trace_summary_from_rows(rows):
    traces = defaultdict(
        lambda: {
            "traceId": "",
            "traceName": "",
            "sessionId": "",
            "userId": "",
            "environment": "",
            "firstStartTime": "",
            "lastEndTime": "",
            "observationCount": 0,
            "generationCount": 0,
            "observationTypes": Counter(),
            "models": Counter(),
            "inputTokens": 0,
            "outputTokens": 0,
            "totalTokens": 0,
            "totalCost": 0.0,
            "totalLatency": 0.0,
            "firstInput": "",
            "finalOutput": "",
            "errorCount": 0,
        }
    )

    for item in rows:
        trace_id = item.get("traceId") or ""
        if not trace_id:
            continue

        row = traces[trace_id]
        row["traceId"] = trace_id
        row["traceName"] = first_non_empty(row["traceName"], item.get("name"))
        row["environment"] = first_non_empty(row["environment"], item.get("environment"))

        start_time = item.get("startTime") or ""
        end_time = item.get("endTime") or ""
        if start_time and (not row["firstStartTime"] or start_time < row["firstStartTime"]):
            row["firstStartTime"] = start_time
        if end_time and (not row["lastEndTime"] or end_time > row["lastEndTime"]):
            row["lastEndTime"] = end_time

        item_type = item.get("type") or ""
        row["observationCount"] += 1
        row["observationTypes"][item_type] += 1
        if item_type == "GENERATION":
            row["generationCount"] += 1

        model = item.get("model") or ""
        if model:
            row["models"][model] += 1

        row["inputTokens"] += int(float(item.get("inputTokens") or 0))
        row["outputTokens"] += int(float(item.get("outputTokens") or 0))
        row["totalTokens"] += int(float(item.get("totalTokens") or 0))
        row["totalCost"] += float(item.get("totalCost") or 0)
        row["totalLatency"] += float(item.get("latency") or 0)

        if not row["firstInput"] and item.get("inputPreview"):
            row["firstInput"] = compact(item.get("inputPreview"))
        if item.get("outputPreview"):
            row["finalOutput"] = compact(item.get("outputPreview"))

    return finalize_trace_summaries(traces)


def build_trace_summary(observations):
    traces = defaultdict(
        lambda: {
            "traceId": "",
            "traceName": "",
            "sessionId": "",
            "userId": "",
            "environment": "",
            "firstStartTime": "",
            "lastEndTime": "",
            "observationCount": 0,
            "generationCount": 0,
            "observationTypes": Counter(),
            "models": Counter(),
            "inputTokens": 0,
            "outputTokens": 0,
            "totalTokens": 0,
            "totalCost": 0.0,
            "totalLatency": 0.0,
            "firstInput": "",
            "finalOutput": "",
            "errorCount": 0,
        }
    )

    for item in observations:
        trace_id = item.get("traceId") or ""
        if not trace_id:
            continue

        row = traces[trace_id]
        row["traceId"] = trace_id
        row["traceName"] = first_non_empty(row["traceName"], item.get("traceName"), item.get("name"))
        row["sessionId"] = first_non_empty(row["sessionId"], item.get("sessionId"))
        row["userId"] = first_non_empty(row["userId"], item.get("userId"))
        row["environment"] = first_non_empty(row["environment"], item.get("environment"))

        start_time = item.get("startTime") or ""
        end_time = item.get("endTime") or ""
        if start_time and (not row["firstStartTime"] or start_time < row["firstStartTime"]):
            row["firstStartTime"] = start_time
        if end_time and (not row["lastEndTime"] or end_time > row["lastEndTime"]):
            row["lastEndTime"] = end_time

        item_type = item.get("type") or ""
        row["observationCount"] += 1
        row["observationTypes"][item_type] += 1
        if item_type == "GENERATION":
            row["generationCount"] += 1

        model = first_non_empty(item.get("model"), item.get("providedModelName"))
        if model:
            row["models"][model] += 1

        row["inputTokens"] += int(usage_value(item, "input") or 0)
        row["outputTokens"] += int(usage_value(item, "output") or 0)
        row["totalTokens"] += int(usage_value(item, "total") or 0)
        row["totalCost"] += float(cost_value(item) or 0)
        row["totalLatency"] += float(item.get("latency") or 0)

        if not row["firstInput"] and item.get("input") not in (None, ""):
            row["firstInput"] = compact(item.get("input"))
        if item.get("output") not in (None, ""):
            row["finalOutput"] = compact(item.get("output"))

        if item.get("level") == "ERROR" or item.get("statusMessage"):
            row["errorCount"] += 1

    return finalize_trace_summaries(traces)


def build_trace_summary_from_iterable(observations):
    traces = defaultdict(
        lambda: {
            "traceId": "",
            "traceName": "",
            "sessionId": "",
            "userId": "",
            "environment": "",
            "firstStartTime": "",
            "lastEndTime": "",
            "observationCount": 0,
            "generationCount": 0,
            "observationTypes": Counter(),
            "models": Counter(),
            "inputTokens": 0,
            "outputTokens": 0,
            "totalTokens": 0,
            "totalCost": 0.0,
            "totalLatency": 0.0,
            "firstInput": "",
            "finalOutput": "",
            "errorCount": 0,
        }
    )
    observation_count = 0

    for item in observations:
        observation_count += 1
        trace_id = item.get("traceId") or ""
        if not trace_id:
            continue

        row = traces[trace_id]
        row["traceId"] = trace_id
        row["traceName"] = first_non_empty(row["traceName"], item.get("traceName"), item.get("name"))
        row["sessionId"] = first_non_empty(row["sessionId"], item.get("sessionId"))
        row["userId"] = first_non_empty(row["userId"], item.get("userId"))
        row["environment"] = first_non_empty(row["environment"], item.get("environment"))

        start_time = item.get("startTime") or ""
        end_time = item.get("endTime") or ""
        if start_time and (not row["firstStartTime"] or start_time < row["firstStartTime"]):
            row["firstStartTime"] = start_time
        if end_time and (not row["lastEndTime"] or end_time > row["lastEndTime"]):
            row["lastEndTime"] = end_time

        item_type = item.get("type") or ""
        row["observationCount"] += 1
        row["observationTypes"][item_type] += 1
        if item_type == "GENERATION":
            row["generationCount"] += 1

        model = first_non_empty(item.get("model"), item.get("providedModelName"))
        if model:
            row["models"][model] += 1

        row["inputTokens"] += int(usage_value(item, "input") or 0)
        row["outputTokens"] += int(usage_value(item, "output") or 0)
        row["totalTokens"] += int(usage_value(item, "total") or 0)
        row["totalCost"] += float(cost_value(item) or 0)
        row["totalLatency"] += float(item.get("latency") or 0)

        if not row["firstInput"] and item.get("input") not in (None, ""):
            row["firstInput"] = compact(item.get("input"))
        if item.get("output") not in (None, ""):
            row["finalOutput"] = compact(item.get("output"))

        if item.get("level") == "ERROR" or item.get("statusMessage"):
            row["errorCount"] += 1

        if observation_count % 1000 == 0:
            print(f"Processed observations: {observation_count}", flush=True)

    return finalize_trace_summaries(traces), observation_count


def finalize_trace_summaries(traces):
    summaries = []
    for row in traces.values():
        summary = dict(row)
        summary["observationTypes"] = ";".join(
            f"{key}:{value}" for key, value in sorted(row["observationTypes"].items()) if key
        )
        summary["models"] = ";".join(
            f"{key}:{value}" for key, value in row["models"].most_common()
        )
        summary["totalCost"] = round(summary["totalCost"], 8)
        summary["totalLatency"] = round(summary["totalLatency"], 3)
        summaries.append(summary)

    summaries.sort(key=lambda item: item.get("firstStartTime", ""), reverse=True)
    return summaries


def write_outputs(summaries, observation_count):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = pipeline_output_path("trace_summary_csv")
    jsonl_path = pipeline_output_path("trace_summary_jsonl")
    stats_path = pipeline_output_path("profile_stats_json")

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
        "observationTypes",
        "models",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "totalCost",
        "totalLatency",
        "errorCount",
        "firstInput",
        "finalOutput",
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)

    with jsonl_path.open("w", encoding="utf-8") as file:
        for row in summaries:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    stats = {
        "observationCount": observation_count,
        "traceCount": len(summaries),
        "sessionCount": len({row["sessionId"] for row in summaries if row["sessionId"]}),
        "generationObservationCount": sum(row["generationCount"] for row in summaries),
        "tracesWithErrors": sum(1 for row in summaries if row["errorCount"] > 0),
        "totalTokens": sum(row["totalTokens"] for row in summaries),
        "totalCost": round(sum(row["totalCost"] for row in summaries), 8),
    }
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    return csv_path, jsonl_path, stats_path, stats


def main():
    if SOURCE.exists():
        summaries, observation_count = build_trace_summary_from_iterable(iter_json_array(SOURCE))
    elif SUMMARY_SOURCE.exists():
        rows = load_summary_rows()
        summaries = build_trace_summary_from_rows(rows)
        observation_count = len(rows)
    else:
        raise RuntimeError("No observations source found.")

    csv_path, jsonl_path, stats_path, stats = write_outputs(summaries, observation_count)

    print(f"Loaded observations: {stats['observationCount']}")
    print(f"Built trace rows: {stats['traceCount']}")
    print(f"Saved: {csv_path}")
    print(f"Saved: {jsonl_path}")
    print(f"Saved: {stats_path}")


if __name__ == "__main__":
    main()
