"use client";
import { useState } from "react";
import { Camera, Download } from "lucide-react";
import { motion } from "framer-motion";

interface Props {
  reportRef: React.RefObject<HTMLDivElement | null>;
  scoresRef: React.RefObject<HTMLDivElement | null>;
  agenticRef: React.RefObject<HTMLDivElement | null>;
}

async function captureElement(
  element: HTMLElement | null,
  filename: string
): Promise<void> {
  if (!element) return;
  const { toPng } = await import("html-to-image");
  const url = await toPng(element, {
    backgroundColor: "#0b0f1a",
    pixelRatio: 2,
  });
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}-${Date.now()}.png`;
  a.click();
}

export default function ScreenshotToolbar({
  reportRef,
  scoresRef,
  agenticRef,
}: Props) {
  const [capturing, setCapturing] = useState<string | null>(null);

  const capture = async (
    ref: React.RefObject<HTMLDivElement | null>,
    key: string,
    filename: string
  ) => {
    setCapturing(key);
    try {
      await captureElement(ref.current, filename);
    } finally {
      setCapturing(null);
    }
  };

  const buttons = [
    {
      key: "full",
      label: "Full Report",
      ref: reportRef,
      filename: "rag-comparison-report",
    },
    {
      key: "scores",
      label: "Scores",
      ref: scoresRef,
      filename: "rag-scoring-dashboard",
    },
    {
      key: "agentic",
      label: "Agentic Trace",
      ref: agenticRef,
      filename: "rag-agentic-trace",
    },
  ];

  return (
    <motion.div
      initial={{ y: 80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-elevated bg-bg/90 backdrop-blur-md"
    >
      <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-3">
        <Camera size={14} className="text-muted shrink-0" />
        <span className="text-xs text-muted mr-2">Capture:</span>

        {buttons.map((btn) => (
          <button
            key={btn.key}
            onClick={() => capture(btn.ref, btn.key, btn.filename)}
            disabled={capturing !== null}
            className="flex items-center gap-1.5 text-xs border border-elevated rounded-button px-3 py-1.5 text-foreground hover:border-cyan/50 hover:text-cyan transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {capturing === btn.key ? (
              <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
            ) : (
              <Download size={11} />
            )}
            {btn.label}
          </button>
        ))}
      </div>
    </motion.div>
  );
}
