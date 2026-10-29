import { FAQ, METHODS, STEPS } from "@/lib/site";
import { Icon } from "./ui";

const METHOD_ICONS = [Icon.blend, Icon.layers, Icon.brush, Icon.crop];

/** Explanatory content under the upload box: how it works, the methods, FAQ. */
export default function LandingContent() {
  return (
    <div className="mx-auto mt-24 max-w-4xl space-y-24">
      <section aria-labelledby="how-it-works">
        <h2 id="how-it-works" className="t-section text-center">
          How to remove the watermark
        </h2>
        <ol className="mt-8 grid gap-4 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="card p-6">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-sm font-semibold text-white">
                {i + 1}
              </span>
              <h3 className="mt-4 text-[1.0625rem] font-semibold tracking-[-0.01em]">{s.title}</h3>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-label-2">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="methods">
        <h2 id="methods" className="t-section text-center">
          Four ways to remove it
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-label-2">
          Every clip is different, so you can preview each method and keep the one that looks best.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {METHODS.map((m, i) => (
            <div key={m.title} className="card flex gap-4 p-6">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                {METHOD_ICONS[i]("h-5 w-5")}
              </span>
              <div>
                <h3 className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{m.title}</h3>
                <p className="mt-1 text-[0.9375rem] leading-relaxed text-label-2">{m.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="faq" className="mx-auto max-w-2xl">
        <h2 id="faq" className="t-section text-center">
          Questions
        </h2>
        {/* Native <details>: works without JavaScript and is fully indexable. */}
        <div className="card mt-8 divide-y divide-separator/[0.08] overflow-hidden">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="group">
              <summary
                className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-[1rem] font-semibold
                  outline-none transition-colors hover:bg-fill/[0.06] focus-visible:bg-accent/[0.08] [&::-webkit-details-marker]:hidden"
              >
                <h3>{q}</h3>
                <span className="shrink-0 text-label-3 transition-transform duration-200 group-open:rotate-45" aria-hidden>
                  {Icon.close("h-4 w-4 rotate-45")}
                </span>
              </summary>
              <p className="px-6 pb-5 text-[0.9375rem] leading-relaxed text-label-2">{a}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
