"use client";
import { useEffect, useRef } from "react";
import { useDemoStore } from "@/store/demoStore";
import { getExperimentConfig, getQuestions } from "@/lib/api";
import HeaderMetadata from "./HeaderMetadata";
import ArchitectureDiagram from "./ArchitectureDiagram";
import DemoControlPanel from "./DemoControlPanel";
import ProcessTracker from "./ProcessTracker";
import BasicRAGPanel from "./BasicRAGPanel";
import AgenticRAGPanel from "./AgenticRAGPanel";
import GroundingPanel from "./GroundingPanel";
import ScoringDashboard from "./ScoringDashboard";
import ScreenshotToolbar from "./ScreenshotToolbar";
import FAQSection from "./FAQSection";

export default function DemoPage() {
  const store = useDemoStore();
  const reportRef = useRef<HTMLDivElement>(null);
  const scoresRef = useRef<HTMLDivElement>(null);
  const agenticRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getExperimentConfig()
      .then(store.setExperimentConfig)
      .catch(console.error);
    getQuestions()
      .then((qs) => {
        store.setQuestions(qs);
        if (qs.length > 0) store.setSelectedQuestion(qs[0].query);
      })
      .catch(console.error);
  }, []);

  const hasResults =
    store.basicRAGResult !== null && store.agenticRAGResult !== null;

  return (
    <div className="min-h-screen bg-bg text-foreground">
      <HeaderMetadata config={store.experimentConfig} />

      <div className="max-w-screen-xl mx-auto px-4 pt-20 pb-32 space-y-8">
        {/* Architecture + Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3">
            <ArchitectureDiagram
              agentSteps={store.agentSteps}
              status={store.status}
            />
          </div>
          <div className="lg:col-span-2">
            <DemoControlPanel />
          </div>
        </div>

        {/* Process Tracker */}
        {store.status !== "idle" && (
          <ProcessTracker
            status={store.status}
            currentStage={store.currentStage}
            agentSteps={store.agentSteps}
            basicRAGPhase={store.basicRAGPhase}
            agenticRAGPhase={store.agenticRAGPhase}
            hasGrounding={store.groundingBasic !== null}
            hasScoring={store.scoreBasic !== null}
          />
        )}

        {/* Error Banner */}
        {store.error && (
          <div className="rounded-card border border-danger/30 bg-danger/10 px-5 py-4 text-danger text-sm">
            {store.error}
          </div>
        )}

        {/* Results */}
        <div ref={reportRef} className="space-y-8">
          {/* Side-by-side RAG results */}
          {(store.basicRAGResult || store.agentSteps.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <BasicRAGPanel result={store.basicRAGResult} />
              <div ref={agenticRef}>
                <AgenticRAGPanel
                  result={store.agenticRAGResult}
                  liveSteps={store.agentSteps}
                  isRunning={store.status === "running"}
                />
              </div>
            </div>
          )}

          {/* Grounding */}
          {store.groundingBasic && store.groundingAgentic && (
            <GroundingPanel
              basic={store.groundingBasic}
              agentic={store.groundingAgentic}
            />
          )}

          {/* Scoring Dashboard */}
          {store.scoreBasic && store.scoreAgentic && (
            <div ref={scoresRef}>
              <ScoringDashboard
                basic={store.scoreBasic}
                agentic={store.scoreAgentic}
                basicLatency={store.basicRAGResult?.latency_s ?? 0}
                agenticLatency={store.agenticRAGResult?.latency_s ?? 0}
                agenticRetries={store.agenticRAGResult?.retry_count ?? 0}
              />
            </div>
          )}
        </div>

        {/* FAQ */}
        <FAQSection />
      </div>

      {store.status === "completed" && (
        <ScreenshotToolbar
          reportRef={reportRef}
          scoresRef={scoresRef}
          agenticRef={agenticRef}
        />
      )}
    </div>
  );
}
