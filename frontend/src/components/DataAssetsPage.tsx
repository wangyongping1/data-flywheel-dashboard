import { useEffect, useState } from "react";
import { AnnotationReview } from "./AnnotationReview";
import { SourceTag } from "./SourceTag";

interface ItemsStats {
  total_candidates: number;
  total_reviewed: number;
  total_approved: number;
}

// Demo 数据：数据质量分层（设计文档规定）
const DEMO_QUALITY_TIERS = [
  { tier: "高质量", count: 64, pct: 60, color: "var(--green)" },
  { tier: "中等质量", count: 28, pct: 26, color: "var(--yellow)" },
  { tier: "需复核", count: 15, pct: 14, color: "var(--orange)" },
];

// Demo 数据：预计节省审核时间
const DEMO_TIME_SAVED = "约 4.2 小时";

export function DataAssetsPage() {
  const [stats, setStats] = useState<ItemsStats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/annotation/items");
        const data = await res.json();
        // items 统计从 AnnotationReview 的统计字段获取
        const items = data.items || [];
        let reviewed = 0;
        let approved = 0;
        for (const it of items) {
          const val = (it.include_in_dataset || "").toLowerCase();
          if (["yes", "y", "true", "1", "no", "n", "false", "0"].includes(val)) reviewed++;
          if (["yes", "y", "true", "1"].includes(val)) approved++;
        }
        setStats({
          total_candidates: items.length,
          total_reviewed: reviewed,
          total_approved: approved,
        });
      } catch {
        setError(true);
      }
    })();
  }, []);

  const hasData = !error && stats && stats.total_candidates > 0;
  const approvalRate = hasData && stats!.total_reviewed > 0
    ? ((stats!.total_approved / stats!.total_reviewed) * 100).toFixed(1)
    : "0";

  return (
    <div className="stage-page">
      <div className="stage-header">
        <h2>数据资产</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="stage-meta">真实反馈如何变成训练就绪的资产</span>
          {hasData ? <SourceTag source="real" /> : <SourceTag source="demo" />}
        </div>
      </div>

      {/* 空状态优雅降级 */}
      {!hasData && (
        <div className="fallback-note">
          当前未检测到真实数据，已切换为演示样例。
        </div>
      )}

      {/* KPI 卡 */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="label">候选样本</div>
          <div className="value">{hasData ? stats!.total_candidates : "300"}</div>
          <div className="detail">问题筛选后</div>
        </div>
        <div className="kpi-card">
          <div className="label">已审核</div>
          <div className="value">{hasData ? stats!.total_reviewed : "300"}</div>
          <div className="detail">人机审核完成</div>
        </div>
        <div className="kpi-card">
          <div className="label">推荐采纳</div>
          <div className="value ok">{hasData ? stats!.total_approved : "107"}</div>
          <div className="detail">进入训练集</div>
        </div>
        <div className="kpi-card">
          <div className="label">采纳率</div>
          <div className="value">{approvalRate}%</div>
          <div className="detail">审核通过比例</div>
        </div>
      </div>

      {/* Demo 数据区：数据质量分层 + 预计节省时间 */}
      <div className="card">
        <div className="section-title">
          <h3>数据质量分层</h3>
          <div><SourceTag source="demo" /></div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {DEMO_QUALITY_TIERS.map((t) => (
            <div key={t.tier} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ minWidth: 80, fontSize: 13, color: "var(--text-muted)" }}>{t.tier}</span>
              <div style={{ flex: 1, height: 12, background: "var(--border-soft)", borderRadius: 999, overflow: "hidden" }}>
                <div style={{ width: `${t.pct}%`, height: "100%", background: t.color, borderRadius: 999 }} />
              </div>
              <span style={{ minWidth: 60, textAlign: "right", fontSize: 13, fontWeight: 600 }}>{t.count} 条</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14, padding: "10px 14px", background: "var(--bg)", borderRadius: 8, fontSize: 13, color: "var(--text-muted)" }}>
          预计节省人工审核时间：<strong style={{ color: "var(--text)" }}>{DEMO_TIME_SAVED}</strong>
        </div>
      </div>

      {/* 业务化分组说明 */}
      <div className="card">
        <div className="section-title">
          <h3>样本分组</h3>
          <div><SourceTag source="real" /></div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <span className="source-label source-real" style={{ textTransform: "none" }}>推荐采纳 · {hasData ? stats!.total_approved : 107} 条</span>
          <span className="source-label source-static" style={{ textTransform: "none" }}>需复核 · 0 条</span>
          <span className="source-label source-demo" style={{ textTransform: "none" }}>不进入训练 · {hasData ? stats!.total_candidates - stats!.total_approved : 193} 条</span>
        </div>
      </div>

      {/* 复用标注审核 UI（含生成训练数据包导出） */}
      <AnnotationReview />
    </div>
  );
}
