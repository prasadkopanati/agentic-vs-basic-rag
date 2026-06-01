"use client";
import { useCallback } from "react";
import { openDemoStream, startDemo } from "@/lib/api";
import { useDemoStore } from "@/store/demoStore";
import type { DemoEvent } from "@/types/demo";

export function useDemoRun() {
  const store = useDemoStore();

  const runDemo = useCallback(async () => {
    if (store.status === "running" || !store.selectedQuestion) return;
    store.resetDemo();
    store.setStatus("running");

    try {
      const { demo_id } = await startDemo(
        store.selectedQuestion,
        store.weightProfile
      );
      store.setDemoId(demo_id);

      const es = openDemoStream(demo_id);

      es.onmessage = (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data) as DemoEvent;
          if (event.event === "heartbeat") return;
          store.handleDemoEvent(event);
          if (event.event === "done" || event.event === "error") {
            es.close();
          }
        } catch {
          // malformed SSE frame — ignore
        }
      };

      es.onerror = () => {
        store.setError("Connection lost. Please try again.");
        es.close();
      };
    } catch (err) {
      store.setError(
        err instanceof Error ? err.message : "Failed to start demo"
      );
    }
  }, [store]);

  return { runDemo, resetDemo: store.resetDemo };
}
