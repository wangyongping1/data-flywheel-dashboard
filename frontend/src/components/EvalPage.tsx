import { useEffect, useState } from "react";
import { api, EvaluationsResponse } from "../api";
import { SourceTag } from "./SourceTag";

export function EvalPage() {
  const [data, setData] = useState<EvaluationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false;
    (async () => {
      try {
        const d = await api.evaluations();
        if (!stopped) setData(d);
      } catch {
        if (!stopped) setError(true);
      } finally {
        if (!stopped) setLoading(false);
      }
    })();
    return () => { stopped = true; };
  }, []);

  const hasData = !error && data;
  const leaderboard = hasData ? data!.leaderboard : [];
  const best = leaderboard.length > 0 ? leaderboard[0] : null;
  const sessions = hasData ? data!.sessions.length : 0;

  return (
    <div className="stage-page">
      <div className="stage-header">
        <h2>效果评估</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="stage-meta">每一次模型迭代上线前都可被衡量</span>
          <SourceTag source="static" />
        </div>
      </div>

      {/* 中文业务摘要 */}
      <div className="eval-summary">
        <div className="es-text">
          {hasData && best ? (
            <>
              已完成 <strong>{sessions}</strong> 轮评估，
              最佳准确率 <strong>{best.accuracy.toFixed(1)}%</strong>
              （{best.agent} + {best.model}）。
              评估体系追踪准确率、耗时、成本，为上线决策提供证据。
            </>
          ) : (
            <>
              当前评估数据为静态快照。评估体系追踪准确率、耗时、成本，为上线决策提供证据。
            </>
          )}
        </div>
        {hasData && best && (
          <span className="source-label source-static">静态快照</span>
        )}
      </div>

      {/* Agent Eval Lab iframe */}
      <div className="eval-lab-embed">
        <iframe src="/eval-lab/" title="Agent Eval Lab" className="eval-lab-iframe" />
      </div>

      {/* baseline vs v1 预测对比（Demo 数据） */}
      <div className="card" style={{ marginTop: 22 }}>
        <div className="section-title">
          <h3>版本对比预测</h3>
          <div><SourceTag source="demo" /></div>
        </div>
        <div className="compare-grid" style={{ marginBottom: 0 }}>
          <div className="compare-card">
            <div className="cc-version">Baseline</div>
            <div className="cc-value">{best ? `${best.accuracy.toFixed(1)}%` : "—"}</div>
            <div className="cc-note">当前线上模型</div>
          </div>
          <div className="compare-card v1">
            <div className="cc-version">v1 预测</div>
            <div className="cc-value">{best ? `${(best.accuracy + 7).toFixed(1)}%` : "—"}</div>
            <div className="cc-note">基于训练样本的预测值</div>
          </div>
        </div>
      </div>
    </div>
  );
}
