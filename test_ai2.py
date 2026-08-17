import csv, json, urllib.request, os
from pathlib import Path
key = os.getenv("AI_ANNOTATOR_API_KEY", "")
annotation_csv = Path(__file__).resolve().parent / "data" / "outputs" / "langfuse_pipeline" / "annotation_batch.csv"
with annotation_csv.open("r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
row = rows[5]
prompt = f"""Rate this conversation for training quality.
Input: {row["firstInput"][:500]}
Output: {row["finalOutput"][:500]}
Return JSON: {{ "include_in_dataset": "yes", "correctness": "5", "safety": "safe", "comment": "ok" }}"""
body = json.dumps({"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1000, "response_format": {"type": "json_object"}}).encode("utf-8")
req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print("Content:", data["choices"][0]["message"]["content"])
print("Finish:", data["choices"][0]["finish_reason"])
print("Tokens:", data["usage"]["total_tokens"])
print("Prompt tokens:", data["usage"]["prompt_tokens"])
