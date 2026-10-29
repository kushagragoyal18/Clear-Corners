"use client";

import { useRef, useState } from "react";
import type { Box } from "@/lib/api";

interface Props {
  before: string;
  after: string;
  width: number;
  height: number;
  focus?: Box; // watermark region to zoom into
}

/**
 * Two stacked stills; "after" is revealed left of the divider.
 * Pressing anywhere moves the divider there immediately and it then tracks the
 * pointer 1:1. Arrow keys work on the handle (Shift for bigger steps).
 */
export default function BeforeAfterSlider({ before, after, width, height, focus }: Props) {
  const [pos, setPos] = useState(50);
  const [zoom, setZoom] = useState(false);
  const [dragging, setDragging] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  const setFromPointer = (clientX: number) => {
    const r = wrap.current!.getBoundingClientRect();
    setPos(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)));
  };

  // Zoom so the watermark box fills ~60% of the view, centred on it.
  let transform = "scale(1)";
  let origin = "50% 50%";
  if (zoom && focus) {
    const s = Math.min(8, 0.6 * Math.min(width / focus.w, height / focus.h));
    origin = `${((focus.x + focus.w / 2) / width) * 100}% ${((focus.y + focus.h / 2) / height) * 100}%`;
    transform = `scale(${Math.max(1, s)})`;
  }
  const img = "absolute inset-0 h-full w-full transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]";

  return (
    <div className="space-y-3">
      <div
        ref={wrap}
        className={`relative w-full touch-none select-none overflow-hidden rounded-2xl bg-black ${dragging ? "cursor-grabbing" : "cursor-ew-resize"}`}
        style={{ aspectRatio: `${width} / ${height}` }}
        onPointerDown={(e) => {
          setFromPointer(e.clientX);
          e.currentTarget.setPointerCapture(e.pointerId);
          setDragging(true);
        }}
        onPointerMove={(e) => dragging && setFromPointer(e.clientX)}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt="Before" draggable={false} className={img} style={{ transform, transformOrigin: origin }} />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={after} alt="After" draggable={false} className={img} style={{ transform, transformOrigin: origin }} />
        </div>

        <div className="pointer-events-none absolute inset-y-0" style={{ left: `${pos}%` }}>
          <div className="absolute inset-y-0 -ml-px w-0.5 bg-white shadow-[0_0_8px_rgb(0_0_0/0.4)]" />
          <div
            role="slider"
            tabIndex={0}
            aria-label="Compare before and after"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pos)}
            onKeyDown={(e) => {
              const step = e.shiftKey ? 10 : 2;
              if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - step));
              if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + step));
            }}
            className={`pointer-events-auto absolute top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center
              rounded-full bg-white text-neutral-700 shadow-[0_2px_12px_rgb(0_0_0/0.35)] outline-none transition-transform duration-100 ease-out
              focus-visible:ring-4 focus-visible:ring-accent/50 ${dragging ? "scale-95" : ""}`}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="m9 7-5 5 5 5M15 7l5 5-5 5" />
            </svg>
          </div>
        </div>

        <span className="glass t-caption pointer-events-none absolute left-3 top-3 rounded-full px-2.5 py-1 font-semibold">After</span>
        <span className="glass t-caption pointer-events-none absolute right-3 top-3 rounded-full px-2.5 py-1 font-semibold">Before</span>
      </div>

      {focus && (
        <div role="radiogroup" aria-label="View" className="inline-flex rounded-full bg-fill/[0.12] p-0.5 text-sm font-medium">
          {[
            { v: false, label: "Full frame" },
            { v: true, label: "Watermark close-up" },
          ].map((o) => (
            <button
              key={o.label}
              role="radio"
              aria-checked={zoom === o.v}
              onClick={() => setZoom(o.v)}
              className={`pressable rounded-full px-3.5 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-accent/40
                ${zoom === o.v ? "bg-surface text-label shadow-[0_1px_3px_rgb(0_0_0/0.12)]" : "text-label-2 hover:text-label"}`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
