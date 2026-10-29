"use client";

import { useEffect, useRef, useState } from "react";
import BeforeAfterSlider from "@/components/BeforeAfterSlider";
import BoxEditor from "@/components/BoxEditor";
import Dropzone, { validateFile } from "@/components/Dropzone";
import LandingContent from "@/components/LandingContent";
import ModeSelector from "@/components/ModeSelector";
import ProgressBar from "@/components/ProgressBar";
import Stepper from "@/components/Stepper";
import { Button, ButtonLink, Icon, Pill, Spinner, Switch } from "@/components/ui";
import {
  BUSY,
  fileUrl,
  getJob,
  startPreview,
  startRender,
  uploadVideo,
  type Box,
  type Job,
  type Mode,
  type RenderParams,
} from "@/lib/api";

const POLL_MS = 1000;
const CONTACT_EMAIL = "kzze.here@gmail.com";

export default function Home() {
  const [job, setJob] = useState<Job | null>(null);
  const [fileName, setFileName] = useState("");
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [mode, setMode] = useState<Mode>("alpha");
  const [hq, setHq] = useState(false);
  // Params of the last finished preview, and a cache-buster for its files.
  const [previewed, setPreviewed] = useState<{ key: string; v: number } | null>(null);
  const lastStatus = useRef<string | null>(null);
  const now = useNow(30_000);

  const params: RenderParams | null = box ? { mode, box, high_quality: hq } : null;
  const paramsKey = box ? JSON.stringify({ mode, box }) : "";
  const busy = !!job && BUSY.includes(job.status);

  // Poll while the backend is working.
  useEffect(() => {
    if (!job || !busy) return;
    const t = setInterval(async () => {
      try {
        setJob(await getJob(job.id));
      } catch (e) {
        setError((e as Error).message);
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [job?.id, busy]); // eslint-disable-line react-hooks/exhaustive-deps

  // React to status transitions.
  useEffect(() => {
    if (!job || job.status === lastStatus.current) return;
    lastStatus.current = job.status;
    if (job.status === "ready" && job.detection && !box) setBox(job.detection.box);
    if (job.status === "preview_ready" && job.params) {
      setPreviewed({ key: JSON.stringify({ mode: job.params.mode, box: job.params.box }), v: Date.now() });
    }
    if (job.status === "error") setError(job.error ?? "Something went wrong while processing the video.");
  }, [job, box]);

  const onFile = async (file: File) => {
    const problem = validateFile(file);
    if (problem) return setError(problem);
    setError(null);
    setFileName(file.name);
    setUpload(0);
    try {
      setJob(await uploadVideo(file, setUpload));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUpload(null);
    }
  };

  const run = async (fn: typeof startPreview) => {
    if (!job || !params) return;
    setError(null);
    try {
      setJob(await fn(job.id, params));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const reset = () => {
    setJob(null);
    setBox(null);
    setPreviewed(null);
    setError(null);
    setFileName("");
    lastStatus.current = null;
  };

  const info = job?.info;
  const editing = !!(job && info && box);
  const previewFresh = previewed?.key === paramsKey;
  const rendering = job?.status === "rendering" || (job?.status === "queued" && job.message === "Queued" && previewFresh);
  const done = job?.status === "done" && job.files.includes("output");
  const step = !editing ? 0 : done || job?.status === "rendering" ? 3 : previewFresh ? 2 : 1;
  const minutesLeft = job ? Math.max(0, Math.ceil((job.expires_at * 1000 - now) / 60_000)) : 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="glass sticky top-0 z-20 border-b border-separator/[0.08]">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <a href="/" className="flex min-w-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-4 focus-visible:ring-accent/30">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo-128.png" alt="" width={32} height={32} className="h-8 w-8 shrink-0" />
            <span className="truncate font-semibold tracking-[-0.01em]">
              Clear Corners
              {/* The descriptor drops on narrow screens so the header fits. */}
              <span className="hidden font-normal text-label-2 sm:inline"> – Watermark Remover</span>
            </span>
          </a>
          <div className="hidden md:block">{job && <Stepper current={step} />}</div>
          <div className="flex min-w-[96px] justify-end">
            {job && (
              <Button variant="ghost" size="sm" className="whitespace-nowrap" onClick={reset}>
                Start over
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 pt-8 sm:px-6 sm:pt-12">
        {job && (
          <div className="mb-6 md:hidden">
            <Stepper current={step} />
          </div>
        )}

        {error && (
          <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl bg-danger/[0.08] p-4 text-danger ring-1 ring-danger/20">
            {Icon.alert("mt-0.5 h-5 w-5 shrink-0")}
            <p className="flex-1 text-[0.9375rem] font-medium">{error}</p>
            <button onClick={() => setError(null)} aria-label="Dismiss" className="pressable -m-1 rounded-full p-1 hover:bg-danger/10">
              {Icon.close("h-4 w-4")}
            </button>
          </div>
        )}

        {/* ---------- Upload ---------- */}
        {!job && (
          <section className="mx-auto max-w-2xl">
            <div className="mb-10 text-center">
              <p className="mb-3 text-sm font-semibold uppercase tracking-[0.08em] text-accent">Clear Corners</p>
              {/* The h1 states what people search for; the brand sits above it. */}
              <h1 className="t-display">Remove the Gemini &amp; Veo watermark.</h1>
              <p className="mx-auto mt-4 max-w-md text-lg leading-relaxed text-label-2">
                Remove the visible logo from videos you generated with Gemini or Veo. Preview the result before you export.
              </p>
            </div>
            {upload === null ? (
              <Dropzone onFile={onFile} />
            ) : (
              <div className="card flex items-center gap-4 p-6">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">{Icon.film("h-6 w-6")}</span>
                <div className="min-w-0 flex-1">
                  <ProgressBar value={upload} label={`Uploading ${fileName}`} />
                </div>
              </div>
            )}
            <ul className="mt-8 grid gap-3 text-sm text-label-2 sm:grid-cols-3">
              {["Finds the logo automatically", "Four removal methods", "Original audio kept"].map((t) => (
                <li key={t} className="flex items-center justify-center gap-2">
                  <span className="text-success">{Icon.check("h-4 w-4")}</span>
                  {t}
                </li>
              ))}
            </ul>
          </section>
        )}
        {!job && <LandingContent />}

        {/* ---------- Analysing ---------- */}
        {job && !editing && job.status !== "error" && (
          <section className="card mx-auto flex max-w-xl flex-col items-center gap-5 px-6 py-12 text-center">
            <Spinner className="h-8 w-8" />
            <div>
              <h2 className="t-title">Finding the watermark…</h2>
              <p className="mt-1 text-label-2">{fileName || "Your video"}</p>
            </div>
            <div className="w-full max-w-sm">
              <ProgressBar value={job.progress} label={job.message || "Analysing"} />
            </div>
          </section>
        )}

        {/* ---------- Adjust / Preview / Export ---------- */}
        {editing && info && box && job && (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-6">
              <section className="card p-4 sm:p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2 px-1">
                  <div>
                    <h2 className="t-title">Watermark area</h2>
                    <p className="text-sm text-label-2">Drag to move, pull a corner to resize. Leave a little margin.</p>
                  </div>
                  {job.detection &&
                    (job.detection.auto ? (
                      <Pill tone="success">
                        {Icon.check("h-3.5 w-3.5")} Found automatically · {Math.round(job.detection.confidence * 100)}%
                      </Pill>
                    ) : (
                      <Pill tone="warning">{Icon.alert("h-3.5 w-3.5")} Not found. Adjust the box</Pill>
                    ))}
                </div>
                <BoxEditor src={fileUrl(job.id, "frame")} width={info.width} height={info.height} box={box} onChange={setBox} />
                <p className="t-caption mt-3 px-1 tabular-nums text-label-3">
                  {info.width}×{info.height} · {info.fps_float.toFixed(info.fps_float % 1 ? 2 : 0)} fps · {info.duration.toFixed(1)} s
                </p>
              </section>

              {previewed && job.files.includes("after") && (
                <section className="card p-4 sm:p-5">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-2 px-1">
                    <h2 className="t-title">Preview</h2>
                    {!previewFresh && <Pill tone="warning">Settings changed. Regenerate to update</Pill>}
                  </div>
                  <div className={`transition-opacity duration-300 ${previewFresh ? "" : "opacity-60"}`}>
                    <BeforeAfterSlider
                      before={fileUrl(job.id, "before", previewed.v)}
                      after={fileUrl(job.id, "after", previewed.v)}
                      width={info.width}
                      height={info.height}
                      focus={box}
                    />
                    <h3 className="mb-2 mt-6 px-1 text-[0.9375rem] font-semibold">3-second clip</h3>
                    <video
                      key={previewed.v}
                      src={fileUrl(job.id, "preview", previewed.v)}
                      controls
                      loop
                      muted
                      autoPlay
                      playsInline
                      className="w-full rounded-2xl bg-black"
                    />
                  </div>
                </section>
              )}
            </div>

            {/* Controls column */}
            <aside className="space-y-6 lg:sticky lg:top-20">
              <section className="card space-y-5 p-5">
                <div>
                  <h2 className="t-title mb-3">Method</h2>
                  <ModeSelector value={mode} onChange={setMode} />
                </div>
                <Switch checked={hq} onChange={setHq} label="High-quality encode" hint="Slower, slightly smaller file at the same quality" />

                <div className="space-y-2.5 border-t border-separator/[0.08] pt-5">
                  {previewFresh ? (
                    <>
                      <Button size="lg" className="w-full" disabled={busy} onClick={() => run(startRender)}>
                        Export full video
                      </Button>
                      <Button variant="secondary" className="w-full" disabled={busy} onClick={() => run(startPreview)}>
                        {Icon.refresh("h-4 w-4")} Regenerate preview
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button size="lg" className="w-full" disabled={busy} onClick={() => run(startPreview)}>
                        Generate preview
                      </Button>
                      <p className="t-caption text-center text-label-3">Check a 3-second preview before exporting.</p>
                    </>
                  )}
                </div>

                {busy && (
                  <div className="rounded-2xl bg-surface-2/70 p-4">
                    <ProgressBar
                      value={job.progress}
                      label={job.message || (rendering ? "Exporting" : job.status === "queued" ? "Waiting to start" : "Working")}
                    />
                  </div>
                )}
              </section>

              {done && (
                <section className="card flex flex-col items-center gap-4 p-6 text-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-full bg-success/[0.12] text-success">
                    {Icon.check("h-7 w-7")}
                  </span>
                  <div>
                    <h2 className="t-title">Your video is ready</h2>
                    <p className="mt-1 text-sm text-label-2">
                      Original audio kept. Available for {minutesLeft} more minute{minutesLeft === 1 ? "" : "s"}.
                    </p>
                  </div>
                  <ButtonLink variant="success" href={fileUrl(job.id, "output")} download className="w-full">
                    {Icon.download("h-5 w-5")} Download
                  </ButtonLink>
                </section>
              )}
            </aside>
          </div>
        )}
      </main>

      <footer className="border-t border-separator/[0.08]">
        <div className="t-caption mx-auto max-w-6xl px-4 py-5 text-center text-label-3 sm:px-6">
          For use on videos you created. Removing the visible mark doesn&apos;t change the video&apos;s AI-generated status.
          <span className="mt-1 block">Uploads and results are deleted automatically after 1 hour.</span>
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="mt-3 inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-medium text-label-2 outline-none
              transition-colors duration-150 hover:text-accent focus-visible:ring-4 focus-visible:ring-accent/30"
          >
            {Icon.mail("h-3.5 w-3.5")}
            Contact: {CONTACT_EMAIL}
          </a>
        </div>
      </footer>
    </div>
  );
}

/** Current time, refreshed every `ms` (for the expiry countdown). */
function useNow(ms: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
