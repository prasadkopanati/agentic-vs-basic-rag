"use client";
import type { AgentStep, DemoStatus } from "@/types/demo";
import MermaidDiagram from "./MermaidDiagram";

interface Props {
  agentSteps: AgentStep[];
  status: DemoStatus;
}

// Maps backend node names to Mermaid node IDs
const NODE_ID: Record<string, string> = {
  rewriter: "RW",
  retriever: "RT",
  grader: "GR",
  retry_counter: "RC",
  generator: "GN",
};

const THEME_INIT = `%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#1f2937', 'primaryTextColor': '#e5e7eb', 'primaryBorderColor': '#4b5563', 'lineColor': '#6b7280', 'background': 'transparent', 'mainBkg': '#1f2937', 'nodeBorder': '#4b5563', 'edgeLabelBackground': '#111827', 'tertiaryColor': '#0b0f1a', 'fontFamily': 'Inter, system-ui, sans-serif', 'fontSize': '12px'}}}%%`;

const BASIC_CHART = `${THEME_INIT}
graph TD
    Q([Query]) --> RT[Retriever]
    RT --> GN[Generator]
    GN --> AN([Answer])
    classDef muted fill:#111827,stroke:#374151,color:#9ca3af
    classDef success fill:#052e16,stroke:#22c55e,color:#22c55e
    class Q muted
    class AN success
`;

function buildAgenticChart(activeNode: string | null): string {
  const mermaidId = activeNode ? NODE_ID[activeNode] : null;

  const activeStyle = mermaidId
    ? `\n    style ${mermaidId} stroke:#06b6d4,stroke-width:2px,fill:#0c2a3a,color:#67e8f9`
    : "";

  return `${THEME_INIT}
graph TD
    Q([Query]) --> RW[Rewriter]
    RW --> RT[Retriever]
    RT --> GR[Grader]
    GR -->|pass| GN[Generator]
    GR -->|fail| RC[Retry Counter]
    RC -.->|retry| RW
    RC -.->|Max Retries| GN
    GN --> AN([Answer ✓])
    linkStyle 4 stroke:#ef4444,color:#ef4444,stroke-dasharray:6 4
    linkStyle 6 stroke:#f59e0b,color:#f59e0b,stroke-dasharray:6 4
    classDef muted fill:#111827,stroke:#374151,color:#9ca3af
    classDef success fill:#052e16,stroke:#22c55e,color:#22c55e
    classDef warning fill:#1c1200,stroke:#f59e0b,color:#f59e0b
    class Q muted
    class AN success
    class RC warning${activeStyle}
`;
}

export default function ArchitectureDiagram({ agentSteps, status }: Props) {
  const latestNode = agentSteps.at(-1)?.node ?? null;
  const agenticChart = buildAgenticChart(latestNode);

  return (
    <div className="rounded-card border border-elevated bg-surface p-5 space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        Pipeline Architecture
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {/* Basic RAG */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider text-center">
            Basic RAG
          </p>
          <MermaidDiagram chart={BASIC_CHART} className="flex justify-center" />
          <p className="text-center text-[10px] text-subtle">
            Single-shot · no quality gate
          </p>
        </div>

        {/* Agentic RAG */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider text-center">
            Agentic RAG
          </p>
          <MermaidDiagram
            chart={agenticChart}
            className="flex justify-center"
          />
          <p className="text-center text-[10px] text-subtle">
            Iterative · LLM grader · retry budget
          </p>
        </div>
      </div>
    </div>
  );
}
