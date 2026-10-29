"use client";

import { useEffect, useRef, useState } from "react";
import type { Box } from "@/lib/api";
import { animateSpring, rubberClamp } from "@/lib/spring";

type Handle = "move" | "nw" | "ne" | "sw" | "se";

interface Props {
  src: string;
  width: number; // natural video width
  height: number;
  box: Box;
  onChange: (b: Box) => void;
}

const MIN = 8;

/**
 * Preview frame with a draggable / resizable watermark box (in video pixels).
 *
 * The box tracks the pointer 1:1 and keeps the grab offset. Dragging past the
 * frame edge rubber-bands, and on release it springs back from wherever it is,
 * so the motion is continuous and can be interrupted by grabbing it again.
 */
export default function BoxEditor({ src, width, height, box, onChange }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const drag = useRef<{ handle: Handle; x0: number; y0: number; box: Box; scale: number } | null>(null);
  // Visual position while rubber-banding / springing; null = show `box` as-is.
  const [visual, setVisual] = useState<{ x: number; y: number } | null>(null);
  const visualRef = useRef<{ x: number; y: number } | null>(null);
  const cancels = useRef<(() => void)[]>([]);
  const [active, setActive] = useState(false);

  const setVis = (v: { x: number; y: number } | null) => {
    visualRef.current = v;
    setVisual(v);
  };
  const stopSprings = () => {
    cancels.current.forEach((c) => c());
    cancels.current = [];
  };
  useEffect(() => stopSprings, []);

  const start = (handle: Handle) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Interrupt: start from where the box is *visually* right now.
    stopSprings();
    const current = visualRef.current ? { ...box, ...visualRef.current } : box;
    const rect = wrap.current!.getBoundingClientRect();
    drag.current = { handle, x0: e.clientX, y0: e.clientY, box: current, scale: width / rect.width };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    setActive(true);
  };

  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.x0) * d.scale;
    const dy = (e.clientY - d.y0) * d.scale;
    let { x, y, w, h } = d.box;
    const right = x + w;
    const bottom = y + h;
    switch (d.handle) {
      case "move": {
        const rx = rubberClamp(x + dx, 0, width - w, width * 0.25);
        const ry = rubberClamp(y + dy, 0, height - h, height * 0.25);
        setVis({ x: rx, y: ry });
        x = clamp(rx, 0, width - w);
        y = clamp(ry, 0, height - h);
        break;
      }
      case "nw":
        x = clamp(x + dx, 0, right - MIN);
        y = clamp(y + dy, 0, bottom - MIN);
        w = right - x;
        h = bottom - y;
        break;
      case "ne":
        y = clamp(y + dy, 0, bottom - MIN);
        w = clamp(w + dx, MIN, width - x);
        h = bottom - y;
        break;
      case "sw":
        x = clamp(x + dx, 0, right - MIN);
        w = right - x;
        h = clamp(h + dy, MIN, height - y);
        break;
      case "se":
        w = clamp(w + dx, MIN, width - x);
        h = clamp(h + dy, MIN, height - y);
        break;
    }
    onChange({ x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) });
  };

  const end = () => {
    drag.current = null;
    setActive(false);
    const v = visualRef.current;
    if (!v) return;
    // Spring back to the committed (clamped) position, X and Y independently.
    const target = { x: clamp(v.x, 0, width - box.w), y: clamp(v.y, 0, height - box.h) };
    const pos = { ...v };
    let doneCount = 0;
    const finish = () => ++doneCount === 2 && setVis(null);
    (["x", "y"] as const).forEach((axis) => {
      cancels.current.push(
        animateSpring(v[axis], target[axis], (val, done) => {
          pos[axis] = val;
          setVis({ ...pos });
          if (done) finish();
        }, { damping: 1, response: 0.4 }),
      );
    });
  };

  const shown = visual ? { ...box, x: visual.x, y: visual.y } : box;
  const pct = (v: number, of: number) => `${(v / of) * 100}%`;

  return (
    <div
      ref={wrap}
      className="relative w-full touch-none select-none overflow-hidden rounded-2xl bg-black"
      style={{ aspectRatio: `${width} / ${height}` }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="Frame from your video" className="absolute inset-0 h-full w-full" draggable={false} />
      <div
        onPointerDown={start("move")}
        className={`absolute cursor-move rounded-md outline outline-2 outline-white/95
          shadow-[0_0_0_9999px_rgb(0_0_0/0.45)] transition-[background-color] duration-150
          ${active ? "bg-white/[0.12]" : "bg-white/[0.04] hover:bg-white/[0.08]"}`}
        style={{ left: pct(shown.x, width), top: pct(shown.y, height), width: pct(shown.w, width), height: pct(shown.h, height) }}
      >
        {(["nw", "ne", "sw", "se"] as const).map((hd) => (
          // Visible 12px knob inside a 32px hit area.
          <span
            key={hd}
            onPointerDown={start(hd)}
            className={`absolute flex h-8 w-8 items-center justify-center
              ${hd.includes("n") ? "-top-4" : "-bottom-4"} ${hd.includes("w") ? "-left-4" : "-right-4"}
              ${hd === "nw" || hd === "se" ? "cursor-nwse-resize" : "cursor-nesw-resize"}`}
          >
            <span className="h-3 w-3 rounded-full bg-white shadow-[0_1px_4px_rgb(0_0_0/0.5)]" />
          </span>
        ))}
        <span
          className={`glass t-caption pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-2.5 py-1
            font-semibold tabular-nums text-label transition-opacity duration-150 ${active ? "opacity-100" : "opacity-0"}`}
        >
          {box.w} × {box.h}
        </span>
      </div>
    </div>
  );
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(Math.max(v, lo), hi);
}
