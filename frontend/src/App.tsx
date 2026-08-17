import { useEffect, useState } from "react";
import { api, FlywheelSummary, PipelineResponse, EventsResponse } from "./api";
import { HealthScore } from "./components/HealthScore";
import { ValueMetrics } from "./components/ValueMetrics";
import { FlywheelPipeline } from "./components/FlywheelPipeline";
import { KeyInsights } from "./components/KeyInsights";
import { EventTimeline } from "./components/EventTimeline";
import { FeedbackPage } from "./components/FeedbackPage";
import { DataAssetsPage } from "./components/DataAssetsPage";
import { ModelIterationPage } from "./components/ModelIterationPage";
import { EvalPage } from "./components/EvalPage";

type Tab = "overview" | "feedback" | "assets" | "iteration" | "eval";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "飞轮总览" },
  { key: "feedback", label: "真实反馈" },
  { key: "assets", label: "数据资产" },
  { key: "iteration", label: "模型迭代" },
  { key: "eval", label: "效果评估" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [summary, setSummary] = useState<FlywheelSummary | null>(null);
  const [pipeline, setPipeline] = useState<PipelineResponse | null>(null);
  const [events, setEvents] = useState<EventsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (tab === "overview") {
      loadData();
    }
  }, [tab]);

  async function loadData() {
    setLoading(true);
    setLoadError(false);
    try {
      const [s, p, e] = await Promise.all([
        api.summary(),
        api.pipeline(),
        api.events(),
      ]);
      setSummary(s);
      setPipeline(p);
      setEvents(e);
    } catch (err) {
      console.error("Failed to load data:", err);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          数据飞轮 Demo
        </div>
        <nav className="pill-nav">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? "active" : ""}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "feedback" ? (
        <FeedbackPage />
      ) : tab === "assets" ? (
        <DataAssetsPage />
      ) : tab === "iteration" ? (
        <ModelIterationPage />
      ) : tab === "eval" ? (
        <EvalPage />
      ) : loading ? (
        <div className="loading">加载飞轮数据中...</div>
      ) : loadError || !summary || !pipeline ? (
        <div className="empty-state">
          当前未检测到真实数据，请确认后端服务已启动。
        </div>
      ) : (
        <>
          {/* Hero */}
          <div className="hero">
            <p className="eyebrow">Data Flywheel</p>
            <h1>数据飞轮让模型持续变好</h1>
            <p className="subtitle">
              从真实业务反馈中发现问题、沉淀训练数据、验证模型迭代效果。
            </p>
            <div className="status-line">
              <span className="dot" />
              {summary.status_line}
            </div>
          </div>

          {/* 健康度 */}
          <HealthScore
            score={summary.health_score}
            label={summary.health_label}
            labelText={summary.health_label_text}
            explanation={summary.health_explanation}
          />

          {/* 4 价值指标 */}
          <ValueMetrics metrics={summary.value_metrics} />

          {/* 飞轮管线 */}
          <FlywheelPipeline data={pipeline} />

          {/* 洞察 + 下一步 */}
          <KeyInsights
            insights={summary.key_insights}
            actions={summary.next_actions}
          />

          {/* 事件时间线 */}
          {events && <EventTimeline events={events.events} />}
        </>
      )}
    </div>
  );
}
