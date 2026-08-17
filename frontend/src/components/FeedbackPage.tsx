import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { api, ObservationsResponse } from "../api";
import { SourceTag } from "./SourceTag";

const fmt = (n: number) => n.toLocaleString();

// Demo 数据：问题分布（设计文档规定）
const DEMO_ISSUE_DIST = [
  { label: "回答不完整", count: 142, pct: 47 },
  { label: "事实错误", count: 89, pct: 30 },
  { label: "安全边界", count: 41, pct: 14 },
  { label: "工具调用失败", count: 28, pct: 9 },
];

// Demo 数据：业务场景标签（设计文档规定）
const DEMO_SCENARIOS = ["售前咨询", "售后支持", "复杂任务执行"];

// Demo 反馈样例（真实明细缺失时降级展示）
const DEMO_FEEDBACK = [
  { scenario: "售前咨询", issue: "回答不完整", snippet: "用户询问产品 A 与产品 B 的差异，模型只覆盖了价格维度，未提及核心功能差异。" },
  { scenario: "售后支持", issue: "事实错误", snippet: "用户询问退换货政策，模型给出了过期的 7 天政策，实际已更新为 15 天。" },
  { scenario: "复杂任务执行", issue: "工具调用失败", snippet: "多步任务执行中第 3 步工具调用参数格式错误，导致后续链路中断。" },
  { scenario: "售前咨询", issue: "回答不完整", snippet: "用户询问套餐对比，模型漏答了企业版的额度限制。" },
  { scenario: "售后支持", issue: "安全边界", snippet: "用户要求查看他人订单，模型未拒绝，存在越权风险。" },
];

export function FeedbackPage() {
  const [data, setData] = useState<ObservationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false;
    (async () => {
      try {
        const d = await api.observations();
        if (!stopped) setData(d);
      } catch {
        if (!stopped) setError(true);
      } finally {
        if (!stopped) setLoading(false);
      }
    })();
    return () => { stopped = true; };
  }, []);

  if (loading) return <div className="loading">加载真实反馈数据...</div>;

  // 空状态优雅降级：不暴露原始错误
  const hasRealData = !error && data && data.summary.total_tokens > 0 && data.trend.length > 0;

  return (
    <div className="stage-page">
      <div className="stage-header">
        <h2>真实反馈</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="stage-meta">飞轮起点：真实业务交互中暴露的问题</span>
          {hasRealData ? (
            <SourceTag source={data!.source} />
          ) : (
            <SourceTag source="demo" />
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 14, color: "var(--text-muted)" }}>
          这些是真实业务交互中暴露出来的问题来源。系统会从反馈中筛出值得训练的样本。
        </p>
      </div>

      {!hasRealData ? (
        // 空状态：业务文案降级，不暴露原始错误
        <>
          <div className="fallback-note">
            当前未检测到真实反馈明细，已切换为演示样例。
          </div>
          <div className="kpi-grid">
            <div className="kpi-card"><div className="label">Traces</div><div className="value muted">—</div></div>
            <div className="kpi-card"><div className="label">总 Token</div><div className="value muted">—</div></div>
            <div className="kpi-card"><div className="label">错误数</div><div className="value muted">—</div></div>
            <div className="kpi-card"><div className="label">总成本</div><div className="value muted">—</div></div>
          </div>
        </>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="label">Traces</div>
              <div className="value">{fmt((data!.kpi as any).total_traces ?? 0)}</div>
            </div>
            <div className="kpi-card">
              <div className="label">总 Token</div>
              <div className="value">{fmt(data!.summary.total_tokens)}</div>
            </div>
            <div className="kpi-card">
              <div className="label">错误数 / 错误率</div>
              <div className="value">
                {data!.summary.total_errors}{" "}
                <span className="muted">/ {(((data!.kpi as any).error_rate ?? 0) * 100).toFixed(1)}%</span>
              </div>
            </div>
            <div className="kpi-card">
              <div className="label">总成本</div>
              <div className="value">${data!.summary.total_cost.toFixed(4)}</div>
            </div>
          </div>

          <div className="card">
            <div className="section-title">
              <h3>每日观测趋势</h3>
              <span>{data!.date_range.start} → {data!.date_range.end} · {data!.summary.buckets} 天</span>
            </div>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={data!.trend} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ecece9" />
                  <XAxis dataKey="date" stroke="#6f737a" fontSize={12} />
                  <YAxis stroke="#6f737a" fontSize={12} />
                  <Tooltip
                    contentStyle={{ background: "#fff", border: "1px solid #d7d7d3", borderRadius: 8 }}
                    labelStyle={{ color: "#111" }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="traces" name="Trace 数" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="errors" name="错误数" stroke="#dc2626" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <div className="section-title">
              <h3>Top Trace（按 Token 用量）</h3>
              <span>真实业务交互</span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Trace</th>
                    <th>模型</th>
                    <th>时间</th>
                    <th>观测数</th>
                    <th>Token</th>
                    <th>错误</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.top_traces.map((t) => (
                    <tr key={t.traceId}>
                      <td title={t.traceId}>{t.traceName || t.traceId.slice(0, 8)}</td>
                      <td className="muted">{t.models || "-"}</td>
                      <td className="muted">{t.firstStartTime?.replace("T", " ").slice(0, 19)}</td>
                      <td>{t.observationCount}</td>
                      <td>{fmt(Number(t.totalTokens) || 0)}</td>
                      <td className={Number(t.errorCount) > 0 ? "err" : "muted"}>{t.errorCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Demo 数据区：问题分布 + 业务场景（始终展示，带 Demo 数据标签） */}
      <div className="card">
        <div className="section-title">
          <h3>问题分布</h3>
          <div><SourceTag source="demo" /></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          {DEMO_ISSUE_DIST.map((d) => (
            <div key={d.label} style={{
              background: "var(--bg)", border: "1px solid var(--border-soft)",
              borderRadius: 10, padding: 14,
            }}>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{d.label}</div>
              <div style={{ fontFamily: "Georgia, serif", fontSize: 26, fontWeight: 700 }}>{d.count}</div>
              <div style={{ fontSize: 11, color: "var(--text-soft)" }}>{d.pct}%</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          <h3>业务场景标签</h3>
          <div><SourceTag source="demo" /></div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {DEMO_SCENARIOS.map((s) => (
            <span key={s} className="source-label source-static" style={{ textTransform: "none" }}>{s}</span>
          ))}
        </div>
      </div>

      {/* 降级时显示 Demo 反馈样例 */}
      {!hasRealData && (
        <div className="card">
          <div className="section-title">
            <h3>反馈样例</h3>
            <div><SourceTag source="demo" /></div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {DEMO_FEEDBACK.map((f, i) => (
              <div key={i} style={{
                border: "1px solid var(--border-soft)", borderRadius: 10, padding: 14,
                background: "var(--bg)",
              }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                  <span className="source-label source-static" style={{ textTransform: "none" }}>{f.scenario}</span>
                  <span className="source-label source-demo">{f.issue}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{f.snippet}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
