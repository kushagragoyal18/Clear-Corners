import type { Mode } from "@/lib/api";
import { Icon, Pill } from "./ui";

const MODES: { id: Mode; title: string; blurb: string; icon: (c?: string) => JSX.Element; badge?: string }[] = [
  { id: "alpha", title: "Reverse blend", blurb: "Works out the logo's transparency and undoes it.", icon: Icon.blend, badge: "Best" },
  { id: "inpaint_temporal", title: "Temporal fill", blurb: "Borrows hidden pixels from nearby frames.", icon: Icon.layers },
  { id: "inpaint_fast", title: "Quick fill", blurb: "Fills each frame from its surroundings.", icon: Icon.brush },
  { id: "crop", title: "Crop & scale", blurb: "Trims the corner away, slightly zoomed.", icon: Icon.crop },
];

export default function ModeSelector({ value, onChange }: { value: Mode; onChange: (m: Mode) => void }) {
  return (
    <div role="radiogroup" aria-label="Removal method" className="divide-y divide-separator/[0.08] overflow-hidden rounded-2xl bg-surface-2/60 ring-1 ring-separator/[0.06]">
      {MODES.map((m) => {
        const on = value === m.id;
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(m.id)}
            className={`flex w-full items-center gap-3 px-3.5 py-3 text-left outline-none transition-colors duration-150
              focus-visible:bg-accent/[0.08] active:bg-fill/[0.12] ${on ? "bg-accent/[0.07]" : "hover:bg-fill/[0.06]"}`}
          >
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors duration-150
                ${on ? "bg-accent text-white" : "bg-fill/[0.14] text-label-2"}`}
            >
              {m.icon("h-[1.15rem] w-[1.15rem]")}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-[0.9375rem] font-semibold">
                {m.title}
                {m.badge && <Pill tone="accent">{m.badge}</Pill>}
              </span>
              <span className="block text-sm leading-snug text-label-2">{m.blurb}</span>
            </span>
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-accent transition-opacity duration-150 ${on ? "opacity-100" : "opacity-0"}`}
            >
              {Icon.check("h-5 w-5")}
            </span>
          </button>
        );
      })}
    </div>
  );
}
