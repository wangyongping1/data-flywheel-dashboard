import { useState, useEffect, useCallback } from "react";

interface AnnotationItem {
  index: number;
  item: {
    traceId: string;
    traceName: string;
    firstInput: string;
    finalOutput: string;
    environment: string;
    models: string;
    include_in_dataset: string;
    correctness: string;
    helpfulness: string;
    hallucination: string;
    safety: string;
    expected_output: string;
    comment: string;
  };
}

interface AIStatus {
  enabled: boolean;
  model: string | null;
  api_base: string | null;
}

interface BatchJob {
  id: string;
  status: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  started_at: string;
  completed_at: string | null;
}

export function AnnotationReview() {
  const [batch, setBatch] = useState<AnnotationItem[]>([]);
  const [totalPending, setTotalPending] = useState(0);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [editBuffer, setEditBuffer] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [aiStatus, setAiStatus] = useState<AIStatus>({ enabled: false, model: null, api_base: null });
  const [aiLoading, setAiLoading] = useState(false);
  const [aiMessage, setAiMessage] = useState("");
  const [batchCount, setBatchCount] = useState(50);
  const [activeJob, setActiveJob] = useState<BatchJob | null>(null);
  const [jobPollInterval, setJobPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [allItems, setAllItems] = useState<AnnotationItem[]>([]);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportMessage, setExportMessage] = useState("");
  const [exportStatus, setExportStatus] = useState<{ exists: boolean; count: number } | null>(null);

  const loadBatch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/annotation/review?count=20");
      const data = await res.json();
      setBatch(data.batch);
      setTotalPending(data.total_pending);
      setCurrentIdx(0);
      if (data.batch.length > 0) {
        setEditBuffer({ ...data.batch[0].item });
      } else if (data.total_pending === 0) {
        const allRes = await fetch("/api/annotation/items");
        const allData = await allRes.json();
        const items: AnnotationItem[] = allData.items.map((item: Record<string, string>, idx: number) => ({ index: idx, item }));
        setAllItems(items);
        setShowAll(true);
        if (items.length > 0) {
          setEditBuffer({ ...items[0].item });
        }
      }
      setSaved(false);
    } catch (err) {
      console.error("Failed to load review batch:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAiStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/annotation/ai-status");
      const data = await res.json();
      setAiStatus(data);
    } catch {
      setAiStatus({ enabled: false, model: null, api_base: null });
    }
  }, []);

  const loadExportStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/annotation/export/status");
      const data = await res.json();
      setExportStatus({ exists: data.exists, count: data.count });
    } catch {
      setExportStatus(null);
    }
  }, []);

  useEffect(() => {
    loadBatch();
    loadAiStatus();
    loadExportStatus();
  }, [loadBatch, loadAiStatus, loadExportStatus]);

  const handleExport = async () => {
    setExportLoading(true);
    setExportMessage("正在导出训练集...");
    try {
      const res = await fetch("/api/annotation/export", { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setExportMessage(`✓ ${data.message}（采纳 ${data.approved_count} / 已审核 ${data.total_reviewed} / 共 ${data.total_candidates}）`);
        loadExportStatus();
      } else {
        setExportMessage(`导出失败: ${data.detail || "未知错误"}`);
      }
    } catch {
      setExportMessage("导出请求失败");
    } finally {
      setExportLoading(false);
      setTimeout(() => setExportMessage(""), 6000);
    }
  };

  useEffect(() => {
    if (activeJob && activeJob.status === "running") {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/annotation/ai-batch/status/${activeJob.id}`);
          const data = await res.json();
          setActiveJob(data);
          if (data.status === "completed") {
            setAiLoading(false);
            setAiMessage(`✓ 完成: ${data.succeeded} 条成功, ${data.failed} 条失败`);
            if (jobPollInterval) clearInterval(jobPollInterval);
            setJobPollInterval(null);
            loadBatch();
            setTimeout(() => setAiMessage(""), 5000);
          }
        } catch {
          setAiLoading(false);
        }
      }, 2000);
      setJobPollInterval(interval);
      return () => clearInterval(interval);
    }
  }, [activeJob?.id, activeJob?.status]);

  const displayItems = showAll ? allItems : batch;
  const current = displayItems[currentIdx];

  const saveAndNext = async () => {
    if (!current) return;
    try {
      const res = await fetch(`/api/annotation/item/${current.index}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editBuffer),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 1000);
        if (currentIdx < displayItems.length - 1) {
          const nextIdx = currentIdx + 1;
          setCurrentIdx(nextIdx);
          setEditBuffer({ ...displayItems[nextIdx].item });
        } else {
          loadBatch();
        }
      }
    } catch (err) {
      console.error("Failed to save:", err);
    }
  };

  const handleSkip = () => {
    if (currentIdx < displayItems.length - 1) {
      const nextIdx = currentIdx + 1;
      setCurrentIdx(nextIdx);
      setEditBuffer({ ...displayItems[nextIdx].item });
    } else {
      loadBatch();
    }
  };

  const handleAiSuggest = async () => {
    if (!current) return;
    setAiLoading(true);
    setAiMessage("");
    try {
      const res = await fetch(`/api/annotation/ai-suggest/${current.index}`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.suggestion) {
        const s = data.suggestion;
        setEditBuffer((prev) => ({
          ...prev,
          include_in_dataset: s.include_in_dataset || prev.include_in_dataset,
          correctness: s.correctness || prev.correctness,
          helpfulness: s.helpfulness || prev.helpfulness,
          safety: s.safety || prev.safety,
          comment: s.comment || prev.comment,
        }));
        setAiMessage("AI 建议已填入，请确认/修改后保存");
      } else {
        setAiMessage(`AI 建议失败: ${data.detail || "未知错误"}`);
      }
    } catch {
      setAiMessage("AI 请求失败");
    } finally {
      setAiLoading(false);
      setTimeout(() => setAiMessage(""), 3000);
    }
  };

  const handleAiBatch = async () => {
    setAiLoading(true);
    setAiMessage(`正在启动 AI 批量标注 ${batchCount} 条...`);
    try {
      const res = await fetch("/api/annotation/ai-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: batchCount, concurrency: 3 }),
      });
      const data = await res.json();
      if (res.ok && data.job_id) {
        setAiMessage(`✓ 任务已启动: ${data.job_id}，正在后台处理...`);
        const statusRes = await fetch(`/api/annotation/ai-batch/status/${data.job_id}`);
        const statusData = await statusRes.json();
        setActiveJob(statusData);
      } else {
        setAiMessage(`启动失败: ${data.detail || "未知错误"}`);
        setAiLoading(false);
      }
    } catch {
      setAiMessage("启动失败");
      setAiLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey) {
      if (e.key === "Enter") {
        e.preventDefault();
        saveAndNext();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        handleSkip();
      }
    }
  };

  const jobProgress = activeJob && activeJob.total > 0
    ? Math.round((activeJob.processed / activeJob.total) * 100)
    : 0;

  if (loading) return <div className="loading">加载审核数据中...</div>;

  return (
    <div className="panel" onKeyDown={handleKeyDown} tabIndex={0}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2>标注审核</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {aiStatus.enabled && (
            <span style={{ fontSize: 11, color: "#22c55e" }}>
              AI: {aiStatus.model}
            </span>
          )}
          <span style={{ fontSize: 13, color: "#94a3b8" }}>
            {showAll
              ? `全部 ${allItems.length} 条 · 当前第 ${currentIdx + 1}/${allItems.length} · 可浏览修改已审核项`
              : totalPending > 0
                ? `${totalPending} 条待审核 · 当前第 ${currentIdx + 1}/${batch.length} 批`
                : "全部已审核完成"
            }
          </span>
        </div>
      </div>

      {aiStatus.enabled && (
        <div className="ai-batch-bar">
          <div className="ai-batch-info">
            <span>AI 批量标注</span>
            <small>后台异步处理，支持进度追踪和失败重试</small>
          </div>
          <div className="ai-batch-controls">
            <label style={{ fontSize: 12, color: "#94a3b8" }}>数量:</label>
            <input
              type="number"
              min={1}
              max={100}
              value={batchCount}
              onChange={(e) => setBatchCount(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
              className="ai-batch-input"
            />
            <button className="btn btn-ai" onClick={handleAiBatch} disabled={aiLoading}>
              {aiLoading && activeJob?.status === "running" ? "运行中..." : "🤖 AI 批量标注"}
            </button>
          </div>
        </div>
      )}

      <div className="export-bar">
        <div className="ai-batch-info">
          <span>训练集导出</span>
          <small>
            {exportStatus?.exists
              ? `training_dataset.jsonl 已生成（${exportStatus.count} 条）`
              : "training_dataset.jsonl 未生成"}
          </small>
        </div>
        <button className="btn btn-primary" onClick={handleExport} disabled={exportLoading}>
          {exportLoading ? "生成中..." : "生成训练数据包"}
        </button>
      </div>

      {exportMessage && <div className="ai-message">{exportMessage}</div>}

      {activeJob && activeJob.status === "running" && (
        <div className="ai-progress">
          <div className="ai-progress-bar">
            <div className="ai-progress-fill" style={{ width: `${jobProgress}%` }} />
          </div>
          <div className="ai-progress-text">
            处理中: {activeJob.processed}/{activeJob.total} ({jobProgress}%)
            · 成功 {activeJob.succeeded} · 失败 {activeJob.failed}
          </div>
        </div>
      )}

      {aiMessage && <div className="ai-message">{aiMessage}</div>}

      {showAll && (
        <div style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-secondary" onClick={() => { setShowAll(false); setCurrentIdx(0); loadBatch(); }}>
            返回待审核
          </button>
          <span style={{ fontSize: 12, color: "#64748b" }}>
            AI 已标注 {allItems.filter(i => i.item.correctness).length}/{allItems.length} 条
          </span>
        </div>
      )}

      {!current ? (
        <div className="loading">暂无数据</div>
      ) : (
        <div className="annotation-card">
          <div className="annotation-header">
            <span className="annotation-id">{current.item.traceId.slice(0, 12)}...</span>
            <span className="annotation-env">{current.item.environment || "production"}</span>
            <span className="annotation-models">{current.item.models || "unknown"}</span>
          </div>

          <div className="annotation-section">
            <div className="annotation-label">用户输入 (Input)</div>
            <div className="annotation-content">{current.item.firstInput || "(空)"}</div>
          </div>

          <div className="annotation-section">
            <div className="annotation-label">模型输出 (Output)</div>
            <div className="annotation-content">{current.item.finalOutput || "(空)"}</div>
          </div>

          <div className="annotation-form">
            <div className="form-row">
              <label>训练决策</label>
              <div className="radio-group">
                {["yes", "no"].map((val) => (
                  <button
                    key={val}
                    className={`radio-btn ${editBuffer.include_in_dataset === val ? "active" : ""}`}
                    onClick={() => setEditBuffer({ ...editBuffer, include_in_dataset: val })}
                  >
                    {val === "yes" ? "推荐采纳" : "不进入训练"}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <label>正确性 (Correctness)</label>
              <div className="radio-group">
                {["", "1", "2", "3", "4", "5"].map((val) => (
                  <button
                    key={val}
                    className={`radio-btn small ${editBuffer.correctness === val ? "active" : ""}`}
                    onClick={() => setEditBuffer({ ...editBuffer, correctness: val })}
                  >
                    {val || "-"}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <label>有用性 (Helpfulness)</label>
              <div className="radio-group">
                {["", "1", "2", "3", "4", "5"].map((val) => (
                  <button
                    key={val}
                    className={`radio-btn small ${editBuffer.helpfulness === val ? "active" : ""}`}
                    onClick={() => setEditBuffer({ ...editBuffer, helpfulness: val })}
                  >
                    {val || "-"}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <label>安全 (Safety)</label>
              <div className="radio-group">
                {["", "safe", "unsafe", "borderline"].map((val) => (
                  <button
                    key={val}
                    className={`radio-btn ${editBuffer.safety === val ? "active" : ""}`}
                    onClick={() => setEditBuffer({ ...editBuffer, safety: val })}
                  >
                    {val || "-"}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <label>备注</label>
              <input
                type="text"
                className="text-input"
                value={editBuffer.comment || ""}
                onChange={(e) => setEditBuffer({ ...editBuffer, comment: e.target.value })}
                placeholder="可选备注..."
              />
            </div>
          </div>

          <div className="annotation-actions">
            <button className="btn btn-primary" onClick={saveAndNext}>
              ✓ 保存并下一条 (Ctrl+Enter)
            </button>
            <button className="btn btn-secondary" onClick={handleSkip}>
              跳过 →
            </button>
            {aiStatus.enabled && (
              <button className="btn btn-ai" onClick={handleAiSuggest} disabled={aiLoading}>
                ✨ AI 建议此条
              </button>
            )}
            {saved && <span className="save-indicator">已保存!</span>}
          </div>
        </div>
      )}
    </div>
  );
}
