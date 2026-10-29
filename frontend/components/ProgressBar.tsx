export default function ProgressBar({ value, label }: { value: number; label?: string }) {
  const v = Math.min(Math.max(value, 0), 1);
  const pct = Math.round(v * 100);
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-4 text-[0.9375rem]">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-label-2">{pct}%</span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-fill/[0.16]"
        role="progressbar"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {/* Animate transform only: scaleX from the left edge. */}
        <div
          className="h-full origin-left rounded-full bg-accent transition-transform duration-500 ease-out will-change-transform"
          style={{ transform: `scaleX(${v})` }}
        />
      </div>
    </div>
  );
}
