interface Props {
  insights: string[];
  actions: string[];
}

export function KeyInsights({ insights, actions }: Props) {
  return (
    <div className="insights-grid">
      <div className="card">
        <div className="section-title">
          <h3>关键洞察</h3>
        </div>
        <ul className="insight-list">
          {insights.map((insight, i) => (
            <li key={i}>{insight}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <div className="section-title">
          <h3>下一步动作</h3>
        </div>
        <ol className="action-list">
          {actions.map((action, i) => (
            <li key={i}>
              <span className="num">{i + 1}</span>
              {action}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
