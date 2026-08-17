import { useEffect, useState } from "react";
import { api, TrainingDetailResponse } from "../api";
import { SourceTag } from "./SourceTag";

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  dry_run: "试跑",
  pending: "进行中",
  failed: "失败",
};

const STATUS_CLASS: Record<string, string> = {
  completed: "ok",
  dry_run: "warn",
  pending: "warn",
  failed: "err",
};

export function ModelIterationPage() {
  const [data, setData] = useState<TrainingDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false;
    (async () => {
      try {
        const d = await api.training();
        if (!stopped) setData(d);
      } catch {
        if (!stopped) setError(true);
      } finally {
        if (!stopped) setLoading(false);
      }
    })();
    return () => { stopped = true; };
  }, []);

  if (loading) return <div className="loading">加载模型迭代数据...</div>;

  // 空状态优雅降级
  const hasData = !error && data;
  const k = hasData ? (data!.kpi as any) : {} as any;
  const proj = hasData ? data!.projection : null;
  const baseline = hasData ? data!.baseline_accuracy : 0;
  const v1Projected = proj?.v1_projected_accuracy ?? 0;

  return (
    <div className="stage-page">
      <div className="stage-header">
        <h2>模型迭代</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="stage-meta">让模型随真实数据持续变好</span>
          {hasData ? <SourceTag source={data!.source} /> : <SourceTag source="pending" />}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 15, color: "var(--text)" }}>
          训练脚本与数据已准备完成。正式训练环境接入后，可生成 v1 模型并进入评估。
        </p>
      </div>

      {/* baseline vs v1 对比 */}
      <div className="compare-grid">
        <div className="compare-card">
          <div className="cc-version">当前版本 · Baseline</div>
          <div className="cc-value">{baseline > 0 ? `${baseline.toFixed(1)}%` : "—"}</div>
          <div className="cc-note">当前最佳评估准确率</div>
          <div style={{ marginTop: 8 }}>
            {baseline > 0 ? <SourceTag source="static" /> : <SourceTag source="pending" />}
          </div>
        </div>
        <div className="compare-card v1">
          <div className="cc-version">下一版本 · v1（预测）</div>
          <div className="cc-value">
            {v1Projected > 0 ? `${v1Projected.toFixed(1)}%` : "—"}
          </div>
          <div className="cc-note">基于 107 条训练样本的预测提升</div>
          <div style={{ marginTop: 8 }}><SourceTag source="demo" /></div>
        </div>
      </div>

      {/* 预计改进指标（Demo 数据） */}
      <div className="card">
        <div className="section-title">
          <h3>预计改进</h3>
          <div><SourceTag source="demo" /></div>
        </div>
        <div className="kpi-grid" style={{ marginBottom: 0 }}>
          <div className="kpi-card">
            <div className="label">预计质量提升</div>
            <div className="value ok">+7.0 pts</div>
            <div className="detail">baseline → v1</div>
          </div>
          <div className="kpi-card">
            <div className="label">人工兜底减少</div>
            <div className="value ok">≈ 12%</div>
            <div className="detail">预测值</div>
          </div>
          <div className="kpi-card">
            <div className="label">训练数据</div>
            <div className="value">107 条</div>
            <div className="detail">已就绪</div>
          </div>
          <div className="kpi-card">
            <div className="label">正式训练</div>
            <div className="value warn">待 GPU 接入</div>
            <div className="detail">dry-run 已验证</div>
          </div>
        </div>
      </div>

      {/* KPI + run 历史 */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="label">总运行数</div>
          <div className="value">{k.total_runs ?? 0}</div>
        </div>
        <div className="kpi-card">
          <div className="label">已完成</div>
          <div className="value">{k.completed_runs ?? 0}</div>
        </div>
        <div className="kpi-card">
          <div className="label">最近运行</div>
          <div className="value small">{hasData && data!.latest_run ? data!.latest_run.run_id : "—"}</div>
        </div>
        <div className="kpi-card">
          <div className="label">最近状态</div>
          <div className={`value ${hasData && data!.latest_run ? STATUS_CLASS[data!.latest_run.status] ?? "" : ""}`}>
            {hasData && data!.latest_run ? (STATUS_LABEL[data!.latest_run.status] ?? data!.latest_run.status) : "—"}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          <h3>训练运行历史</h3>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>模型</th>
                <th>时间</th>
                <th>状态</th>
                <th>指标</th>
              </tr>
            </thead>
            <tbody>
              {hasData && data!.runs.length > 0 ? (
                data!.runs.map((r) => (
                  <tr key={r.run_id}>
                    <td title={r.run_id}>{r.run_id}</td>
                    <td className="muted">{r.model}</td>
                    <td className="muted">{r.timestamp?.replace("T", " ").slice(0, 19)}</td>
                    <td className={STATUS_CLASS[r.status] ?? ""}>{STATUS_LABEL[r.status] ?? r.status}</td>
                    <td className="muted">
                      {Object.keys(r.metrics).length === 0
                        ? "—"
                        : Object.entries(r.metrics).map(([k2, v]) => `${k2}=${v}`).join(", ")}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", color: "var(--text-soft)", padding: 24 }}>
                    暂无训练记录。训练数据与脚本已就绪，等待 GPU 环境接入后可启动正式训练。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          <h3>训练配置</h3>
          {hasData && <span className="muted small">{data!.config_path}</span>}
        </div>
        <pre className="config-block">{hasData ? (data!.config_text || "config.yaml 不存在") : "配置文件待加载"}</pre>
      </div>
    </div>
  );
}
