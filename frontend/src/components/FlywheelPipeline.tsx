import { PipelineResponse } from "../api";
import { SourceTag } from "./SourceTag";

interface Props {
  data: PipelineResponse;
}

export function FlywheelPipeline({ data }: Props) {
  return (
    <div className="pipeline">
      <div className="section-title">
        <h3>飞轮管线</h3>
        <span>真实反馈 → 问题筛选 → 人机审核 → 训练数据 → 模型迭代 → 效果评估</span>
      </div>
      <div className="pipeline-flow">
        {data.stages.map((stage, i) => (
          <div key={stage.name} style={{ display: "flex", alignItems: "stretch", gap: 6 }}>
            <div className="pipeline-node">
              <div className="pn-label">{stage.label}</div>
              <div className="pn-count">
                {stage.count > 0 ? stage.count.toLocaleString() : "—"}
              </div>
              <div className="pn-detail">{stage.detail}</div>
              <div className="pn-source">
                <SourceTag source={stage.source} />
              </div>
            </div>
            {i < data.stages.length - 1 && (
              <div className="pipeline-arrow">→</div>
            )}
          </div>
        ))}
      </div>
      {data.bottleneck && (
        <div className="bottleneck-bar">⚠️ {data.bottleneck_reason}</div>
      )}
    </div>
  );
}
