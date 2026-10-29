import { Icon } from "./ui";

export const STEPS = ["Upload", "Adjust", "Preview", "Export"] as const;

/** Where am I / what's next: a compact step indicator. */
export default function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-1.5 text-sm" aria-label="Progress">
      {STEPS.map((s, i) => {
        const done = i < current;
        const on = i === current;
        return (
          <li key={s} className="flex items-center gap-1.5" aria-current={on ? "step" : undefined}>
            <span
              className={`flex h-6 min-w-6 items-center justify-center gap-1 rounded-full font-medium transition-colors duration-200
                ${on ? "bg-accent px-2.5 text-white" : done ? "text-accent sm:px-2.5" : "text-label-3 sm:px-2.5"}`}
            >
              {done && Icon.check("h-3.5 w-3.5")}
              {/* On narrow screens only the current step is spelled out. */}
              {!done && !on && <span className="tabular-nums sm:hidden">{i + 1}</span>}
              <span className={on ? "" : "hidden sm:inline"}>{s}</span>
            </span>
            {i < STEPS.length - 1 && <span className={`h-px w-3 sm:w-5 ${done ? "bg-accent/50" : "bg-separator/15"}`} />}
          </li>
        );
      })}
    </ol>
  );
}
