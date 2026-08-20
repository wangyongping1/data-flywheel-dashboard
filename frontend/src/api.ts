// 数据来源标签 key（后端返回英文，前端映射到中文）
export type SourceLabel = "real" | "static" | "demo" | "pending" | "stale";

export interface ValueMetric {
  key: string;
  label: string;
  value: string;
  unit: string;
  source: SourceLabel;
}

export interface Projection {
  baseline_accuracy: number;
  v1_projected_accuracy: number;
  projected_gain_pts: number;
  source: SourceLabel;
}

export interface FlywheelSummary {
  generated_at: string;
  health_score: number;
  health_label: "healthy" | "partial" | "stalled";
  health_label_text: string;
  health_explanation: string;
  status_line: string;
  value_metrics: ValueMetric[];
  projection: Projection;
  key_insights: string[];
  next_actions: string[];
  stages: {
    observation: StageInfo;
    dataset: StageInfo;
    training: TrainingStageInfo;
    evaluation: StageInfo;
  };
}

export interface StageInfo {
  status: string;
  source: SourceLabel;
  [key: string]: unknown;
}

export interface TrainingRun {
  run_id: string;
  model: string;
  status: string;
  metrics: Record<string, number>;
}

export interface TrainingStageInfo extends StageInfo {
  total_runs: number;
  completed_runs: number;
  last_run_at: string | null;
  latest_run: TrainingRun | null;
}

export interface PipelineStage {
  name: string;
  label: string;
  count: number;
  detail: string;
  source: SourceLabel;
}

export interface PipelineResponse {
  generated_at: string;
  stages: PipelineStage[];
  bottleneck: string;
  bottleneck_reason: string;
}

export interface FlywheelEvent {
  id: string;
  timestamp: string;
  stage: string;
  type: string;
  title: string;
  detail: string;
  metrics: Record<string, number>;
}

export interface EventsResponse {
  generated_at: string;
  events: FlywheelEvent[];
}

export interface EvalResult {
  task: string;
  agent: string;
  provider: string;
  model: string;
  accuracy: number;
  ci: number;
  passed: number;
  failed: number;
  total: number;
  avg_time_sec: number;
  avg_cost: number;
}

export interface EvalSession {
  session_id: string;
  timestamp: string;
  results: EvalResult[];
}

export interface LeaderboardEntry {
  rank: number;
  agent: string;
  model: string;
  accuracy: number;
  total: number;
}

export interface EvaluationsResponse {
  generated_at: string;
  sessions: EvalSession[];
  leaderboard: LeaderboardEntry[];
}

export interface VerticalEvalSummary {
  total_sessions: number;
  total_trials: number;
  best_accuracy: number;
  best_config: { agent: string; model: string; task: string } | null;
  last_eval_at: string | null;
}

export interface VerticalEvaluationsResponse {
  generated_at: string;
  source: SourceLabel;
  sessions: EvalSession[];
  leaderboard: LeaderboardEntry[];
  summary: VerticalEvalSummary;
}

export interface ObservationBucket {
  date: string;
  traces: number;
  observations: number;
  input_tokens: number;
  output_tokens: number;
  tokens: number;
  cost: number;
  errors: number;
}

export interface TopTrace {
  traceId: string;
  traceName: string;
  firstStartTime: string;
  models: string;
  environment: string;
  observationCount: string;
  totalTokens: string;
  totalCost: string;
  errorCount: string;
}

export interface ObservationsResponse {
  generated_at: string;
  kpi: Record<string, unknown>;
  date_range: { start: string | null; end: string | null };
  trend: ObservationBucket[];
  top_traces: TopTrace[];
  summary: {
    total_tokens: number;
    total_cost: number;
    total_errors: number;
    buckets: number;
  };
  source: SourceLabel;
}

export interface TrainingRunFull {
  run_id: string;
  timestamp: string;
  model: string;
  status: string;
  metrics: Record<string, number>;
}

export interface TrainingDetailResponse {
  generated_at: string;
  kpi: Record<string, unknown>;
  runs: TrainingRunFull[];
  latest_run: TrainingRunFull | null;
  config_path: string;
  config_text: string;
  projection: Projection;
  baseline_accuracy: number;
  source: SourceLabel;
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  summary: () => fetchJSON<FlywheelSummary>("/api/flywheel/summary"),
  pipeline: () => fetchJSON<PipelineResponse>("/api/flywheel/pipeline"),
  events: () => fetchJSON<EventsResponse>("/api/flywheel/events"),
  evaluations: () => fetchJSON<EvaluationsResponse>("/api/flywheel/evaluations"),
  verticalEvaluations: () => fetchJSON<VerticalEvaluationsResponse>("/api/flywheel/evaluations/vertical"),
  observations: () => fetchJSON<ObservationsResponse>("/api/flywheel/observations"),
  training: () => fetchJSON<TrainingDetailResponse>("/api/flywheel/training"),
  triggerLangfuseSync: (forceFull = false) =>
    fetchJSON<{ status: string; job_id: string; message: string }>("/api/import/langfuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force_full: forceFull }),
    }),
  langfuseSyncJobs: () => fetchJSON<{ jobs: any[] }>("/api/import/jobs"),
};

// 数据来源标签中文映射
export const SOURCE_LABEL_TEXT: Record<SourceLabel, string> = {
  real: "真实接入",
  static: "静态快照",
  demo: "Demo 数据",
  pending: "待接入",
  stale: "数据过期",
};
