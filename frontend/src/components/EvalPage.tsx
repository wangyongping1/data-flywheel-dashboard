import { useEffect, useState } from "react";
import { api, EvaluationsResponse, VerticalEvaluationsResponse } from "../api";
import { SourceTag } from "./SourceTag";

export function EvalPage() {
  const [data, setData] = useState<EvaluationsResponse | null>(null);
  const [vertical, setVertical] = useState<VerticalEvaluationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false;
    (async () => {
      try {
        const [d, v] = await Promise.all([
          api.evaluations(),
          api.verticalEvaluations(),
        ]);
        if (!stopped) {
          setData(d);
          setVertical(v);
        }
      } catch {
        if (!stopped) setError(true);
      } finally {
        if (!stopped) setLoading(false);
      }
    })();
    return () => { stopped = true; };
  }, []);

  if (loading) return <div className="loading">加载评估数据...</div>;
  if (error) return <div className="loading">评估数据加载失败</div>;

  const hasData = !!data;
  const leaderboard = hasData ? data!.leaderboard : [];
  const best = leaderboard.length > 0 ? leaderboard[0] : null;
  const sessions = hasData ? data!.sessions.length : 0;

  // 垂直评测集
  const vHas = !!vertical;
  const vSource = vHas ? vertical!.source : "pending";
  const vBoard = vHas ? vertical!.leaderboard : [];
  const vBest = vBoard.length > 0 ? vBoard[0] : null;
  const vSessions = vHas ? vertical!.sessions.length : 0;
  const vSummary = vHas ? vertical!.summary : null;

  return (
    <div className="stage-page">
      <div className="stage-header">
        <h2>效果评估</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="stage-meta">每一次模型迭代上线前都可被衡量</span>
          <SourceTag source="static" />
        </div>
      </div>

      {/* 双评测轨道摘要 */}
      <div className="eval-tracks">
        <div className="eval-track-card">
          <div className="etc-header">
            <span className="etc-title">公共业务评测集</span>
            <SourceTag source="static" />
          </div>
          <div className="etc-body">
            {hasData && best ? (
              <>
                <div className="etc-value">{best.accuracy.toFixed(1)}%</div>
                <div className="etc-note">
                  {sessions} 轮 · {best.agent} + {best.model}
                </div>
              </>
            ) : (
              <div className="etc-note">暂无数据</div>
            )}
          </div>
          <div className="etc-desc">通用 Agent 能力（terminal-bench 等）</div>
        </div>

        <div className="eval-track-card">
          <div className="etc-header">
            <span className="etc-title">垂直业务评测集</span>
            <SourceTag source={vSource} />
          </div>
          <div className="etc-body">
            {vBest ? (
              <>
                <div className="etc-value">{vBest.accuracy.toFixed(1)}%</div>
                <div className="etc-note">
                  {vSessions} 轮 · {vBest.agent} + {vBest.model}
                </div>
              </>
            ) : (
              <div className="etc-note">等待接入真实数据</div>
            )}
          </div>
          <div className="etc-desc">领域专属任务（业务对话/工单/知识问答等）</div>
        </div>
      </div>

      {/* 中文业务摘要 */}
      <div className="eval-summary">
        <div className="es-text">
          {hasData && best ? (
            <>
              公共集已完成 <strong>{sessions}</strong> 轮评估，最佳准确率 <strong>{best.accuracy.toFixed(1)}%</strong>
              （{best.agent} + {best.model}）。
              {vBest ? (
                <>垂直集最佳 <strong>{vBest.accuracy.toFixed(1)}%</strong>，双轨评估为上线决策提供证据。</>
              ) : (
                <>垂直评测集待接入，将补充领域专属能力衡量。</>
              )}
            </>
          ) : (
            <>评估体系追踪准确率、耗时、成本，为上线决策提供证据。垂直评测集将补充领域专属能力衡量。</>
          )}
        </div>
      </div>

      {/* 垂直业务评测集排行榜 */}
      <div className="card">
        <div className="section-title">
          <h3>垂直业务评测集 · 排行榜</h3>
          <div><SourceTag source={vSource} /></div>
        </div>
        {vBoard.length === 0 ? (
          <div className="eval-empty">
            <div className="eval-empty-title">暂无垂直评测数据</div>
            <div className="eval-empty-hint">
              将领域评测结果放入 <code>data/outputs/evaluation/vertical_results/&#123;session&#125;/report.json</code>
              即可自动展示。格式与公共集 <code>report.json</code> 一致（key 为 <code>task__agent__model</code>）。
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Agent</th>
                <th>Model</th>
                <th>准确率</th>
                <th>试验数</th>
                <th>最近评估</th>
              </tr>
            </thead>
            <tbody>
              {vBoard.map((entry) => (
                <tr key={`${entry.agent}-${entry.model}`}>
                  <td className={`rank-${entry.rank <= 3 ? entry.rank : ""}`}>{entry.rank}</td>
                  <td>{entry.agent}</td>
                  <td>{entry.model}</td>
                  <td style={{ fontWeight: 600 }}>{entry.accuracy.toFixed(1)}%</td>
                  <td>{entry.total}</td>
                  <td className="muted">
                    {vSummary?.last_eval_at ? vSummary.last_eval_at.replace("T", " ").slice(0, 19) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Agent Eval Lab iframe（公共集详情） */}
      <div className="card">
        <div className="section-title">
          <h3>公共业务评测集 · Agent Eval Lab</h3>
          <div><SourceTag source="static" /></div>
        </div>
        <div className="eval-lab-embed">
          <iframe src="/eval-lab/" title="Agent Eval Lab" className="eval-lab-iframe" />
        </div>
      </div>

      {/* baseline vs v1 预测对比（Demo 数据） */}
      <div className="card">
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
