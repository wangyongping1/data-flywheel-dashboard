import { SOURCE_LABEL_TEXT, SourceLabel } from "../api";

export function SourceTag({ source }: { source: SourceLabel | string }) {
  const cls = `source-label source-${source}`;
  return (
    <span className={cls}>
      {SOURCE_LABEL_TEXT[source as SourceLabel] || source}
    </span>
  );
}
