// Small shared primitives: buttons, switch, icons, status pill.

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "success";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent/90",
  success: "bg-success text-white hover:bg-success/90",
  secondary: "bg-fill/[0.14] text-label hover:bg-fill/20",
  ghost: "text-accent hover:bg-accent/10",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-8 px-3.5 text-sm", md: "h-11 px-5 text-[0.9375rem]", lg: "h-12 px-6 text-base" };
  return (
    <button
      {...props}
      className={`pressable inline-flex select-none items-center justify-center gap-2 rounded-full font-semibold
        outline-none focus-visible:ring-4 focus-visible:ring-accent/30 disabled:cursor-not-allowed disabled:opacity-40
        ${sizes[size]} ${VARIANTS[variant]} ${className}`}
    />
  );
}

export function ButtonLink({ variant = "primary", className = "", ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant }) {
  return (
    <a
      {...props}
      className={`pressable inline-flex h-12 select-none items-center justify-center gap-2 rounded-full px-6 font-semibold
        outline-none focus-visible:ring-4 focus-visible:ring-accent/30 ${VARIANTS[variant]} ${className}`}
    />
  );
}

export function Switch({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4">
      <span>
        <span className="block text-[0.9375rem] font-medium">{label}</span>
        {hint && <span className="t-caption block text-label-2">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-[31px] w-[51px] shrink-0 rounded-full outline-none transition-colors duration-200
          focus-visible:ring-4 focus-visible:ring-accent/30 ${checked ? "bg-success" : "bg-fill/30"}`}
      >
        <span
          className="absolute left-[2px] top-[2px] h-[27px] w-[27px] rounded-full bg-white shadow-[0_3px_8px_rgb(0_0_0/0.15),0_1px_1px_rgb(0_0_0/0.16)]
            transition-transform duration-200 ease-out"
          style={{ transform: `translateX(${checked ? 20 : 0}px)` }}
        />
      </button>
    </label>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: "neutral" | "success" | "warning" | "accent"; children: ReactNode }) {
  const tones = {
    neutral: "bg-fill/[0.14] text-label-2",
    success: "bg-success/[0.12] text-success",
    warning: "bg-warning/[0.12] text-warning",
    accent: "bg-accent/[0.12] text-accent",
  };
  return <span className={`t-caption inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`h-5 w-5 animate-spin text-label-2 ${className}`} aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

// --- Icons (original, 24px grid, stroke = currentColor) -----------------------

const icon = (d: ReactNode, className = "h-5 w-5") => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
    {d}
  </svg>
);

export const Icon = {
  upload: (c?: string) => icon(<><path d="M12 15V4" /><path d="m7.5 8.5 4.5-4.5 4.5 4.5" /><path d="M5 14v3.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V14" /></>, c),
  check: (c?: string) => icon(<path d="m5 12.5 4.5 4.5L19 7.5" />, c),
  alert: (c?: string) => icon(<><path d="M12 8v5" /><path d="M12 16.5h.01" /><path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></>, c),
  download: (c?: string) => icon(<><path d="M12 4v11" /><path d="m7.5 10.5 4.5 4.5 4.5-4.5" /><path d="M5 20h14" /></>, c),
  refresh: (c?: string) => icon(<><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>, c),
  close: (c?: string) => icon(<><path d="M6 6l12 12" /><path d="M18 6 6 18" /></>, c),
  sparkle: (c?: string) => icon(<path d="M12 3c.6 4.2 2.8 6.4 7 7-4.2.6-6.4 2.8-7 7-.6-4.2-2.8-6.4-7-7 4.2-.6 6.4-2.8 7-7Z" />, c),
  blend: (c?: string) => icon(<><circle cx="9" cy="12" r="5.5" /><circle cx="15" cy="12" r="5.5" /></>, c),
  layers: (c?: string) => icon(<><path d="m12 4 8 4-8 4-8-4 8-4Z" /><path d="m4 12 8 4 8-4" /><path d="m4 16 8 4 8-4" /></>, c),
  brush: (c?: string) => icon(<><path d="M14.5 4.5 19.5 9.5 11 18l-5-5 8.5-8.5Z" /><path d="M6 13c-2 0-3 1.5-3 3.5V20h3.5c2 0 3.5-1 3.5-3" /></>, c),
  crop: (c?: string) => icon(<><path d="M6 2v14a2 2 0 0 0 2 2h14" /><path d="M2 6h14a2 2 0 0 1 2 2v14" /></>, c),
  mail: (c?: string) => icon(<><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></>, c),
  film: (c?: string) => icon(<><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4" /></>, c),
};
