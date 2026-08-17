import { ValueMetric } from "../api";
import { SourceTag } from "./SourceTag";

interface Props {
  metrics: ValueMetric[];
}

export function ValueMetrics({ metrics }: Props) {
  return (
    <div className="value-grid">
      {metrics.map((m) => (
        <div className="value-card" key={m.key}>
          <div className="vc-label">{m.label}</div>
          <div className="vc-value">
            {m.value}
            {m.unit && <span className="unit">{m.unit}</span>}
          </div>
          <div className="vc-source">
            <SourceTag source={m.source} />
          </div>
        </div>
      ))}
    </div>
  );
}
