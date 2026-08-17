import { FlywheelEvent } from "../api";

interface Props {
  events: FlywheelEvent[];
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

const STAGE_LABELS: Record<string, string> = {
  observation: "观测",
  dataset: "数据",
  training: "训练",
  evaluation: "评估",
};

export function EventTimeline({ events }: Props) {
  return (
    <div className="card">
      <div className="section-title">
        <h3>飞轮事件时间线</h3>
        <span>近期飞轮活动</span>
      </div>
      <div className="timeline">
        {events.length === 0 ? (
          <div className="muted" style={{ fontSize: 13, padding: 12 }}>
            当前未检测到真实事件，已切换为演示样例。
          </div>
        ) : (
          events.map((evt) => (
            <div className={`timeline-item ${evt.stage}`} key={evt.id}>
              <div className="timeline-time">
                {formatTime(evt.timestamp)}
                <br />
                <span style={{ fontSize: 10, color: "var(--text-soft)" }}>
                  {STAGE_LABELS[evt.stage] || evt.stage}
                </span>
              </div>
              <div className="timeline-content">
                <div className="title">{evt.title}</div>
                <div className="detail">{evt.detail}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
