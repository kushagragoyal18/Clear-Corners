// Tiny spring animator parameterised the Apple way: damping ratio + response.
//   damping 1.0 = critically damped (no overshoot), < 1 bounces.
//   response    = roughly the seconds it takes to settle; lower is snappier.
// Animations start from the current value and carry an initial velocity, so they
// can be interrupted and restarted mid-flight without a visible seam.

export interface SpringOptions {
  damping?: number;
  response?: number;
  velocity?: number; // units per second
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Animate `from` -> `to`, calling `onUpdate` every frame. Returns a cancel function. */
export function animateSpring(
  from: number,
  to: number,
  onUpdate: (value: number, done: boolean) => void,
  { damping = 1, response = 0.4, velocity = 0 }: SpringOptions = {},
): () => void {
  if (prefersReducedMotion() || from === to) {
    onUpdate(to, true);
    return () => {};
  }
  const stiffness = (2 * Math.PI / response) ** 2; // unit mass
  const friction = (4 * Math.PI * damping) / response;
  let x = from;
  let v = velocity;
  let last = performance.now();
  let raf = 0;

  const step = (now: number) => {
    // Fixed small sub-steps keep the integration stable on slow frames.
    let dt = Math.min((now - last) / 1000, 0.064);
    last = now;
    while (dt > 0) {
      const h = Math.min(dt, 1 / 240);
      v += (-stiffness * (x - to) - friction * v) * h;
      x += v * h;
      dt -= h;
    }
    const done = Math.abs(x - to) < 0.05 && Math.abs(v) < 0.5;
    onUpdate(done ? to : x, done);
    if (!done) raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}

/** Progressive resistance past an edge (iOS-style rubber-banding). */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
}

/** Clamp `v` to [lo, hi], rubber-banding whatever lies outside. */
export function rubberClamp(v: number, lo: number, hi: number, dimension: number): number {
  if (v < lo) return lo + rubberband(v - lo, dimension);
  if (v > hi) return hi + rubberband(v - hi, dimension);
  return v;
}
