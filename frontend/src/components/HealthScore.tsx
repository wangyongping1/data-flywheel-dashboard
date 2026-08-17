interface Props {
  score: number;
  label: "healthy" | "partial" | "stalled";
  labelText: string;
  explanation: string;
}

export function HealthScore({ score, label, labelText, explanation }: Props) {
  return (
    <div className="health-block">
      <div className="health-score">
        {score}
        <span className="denom"> / 100</span>
      </div>
      <div className="health-info">
        <span className={`health-badge ${label}`}>{labelText}</span>
        <div className="health-bar-bg">
          <div
            className={`health-bar-fill ${label}`}
            style={{ width: `${score}%` }}
          />
        </div>
        <p className="explanation" style={{ marginTop: 10 }}>{explanation}</p>
      </div>
    </div>
  );
}
