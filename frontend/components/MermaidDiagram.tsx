"use client";
import { useEffect, useRef, useId } from "react";

interface Props {
  chart: string;
  className?: string;
}

export default function MermaidDiagram({ chart, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const uid = useId().replace(/:/g, "");

  useEffect(() => {
    if (!ref.current) return;
    let cancelled = false;

    import("mermaid").then(({ default: mermaid }) => {
      if (cancelled) return;

      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          primaryColor: "#1f2937",
          primaryTextColor: "#e5e7eb",
          primaryBorderColor: "#4b5563",
          lineColor: "#6b7280",
          background: "transparent",
          mainBkg: "#1f2937",
          nodeBorder: "#4b5563",
          edgeLabelBackground: "#111827",
          tertiaryColor: "#0b0f1a",
          fontFamily: "var(--font-inter, Inter, system-ui, sans-serif)",
          fontSize: "12px",
        },
        flowchart: { useMaxWidth: false },
      });

      mermaid
        .render(`mmd-${uid}`, chart)
        .then(({ svg }) => {
          if (cancelled || !ref.current) return;
          ref.current.innerHTML = svg;
          const svgEl = ref.current.querySelector("svg");
          if (svgEl) {
            // Render at natural font-driven size, centred, no background
            svgEl.removeAttribute("style");
            svgEl.style.display = "block";
            svgEl.style.margin = "0 auto";
            svgEl.style.background = "transparent";
          }
        })
        .catch(console.error);
    });

    return () => {
      cancelled = true;
    };
  }, [chart, uid]);

  return <div ref={ref} className={className} />;
}
