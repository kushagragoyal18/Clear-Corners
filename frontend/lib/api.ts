// Thin client for the FastAPI backend.

// A trailing slash would produce "//api/..." URLs, so strip it.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type Mode = "alpha" | "inpaint_fast" | "inpaint_temporal" | "crop";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type JobStatus =
  | "created"
  | "queued"
  | "analyzing"
  | "ready"
  | "previewing"
  | "preview_ready"
  | "rendering"
  | "done"
  | "error";

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  message: string;
  error: string | null;
  info: { width: number; height: number; duration: number; fps_float: number } | null;
  detection: { box: Box; confidence: number; corner: string; auto: boolean } | null;
  params: { mode: Mode; box: Box; high_quality: boolean } | null;
  files: string[];
  expires_at: number;
}

export interface RenderParams {
  mode: Mode;
  box: Box;
  high_quality: boolean;
}

export const BUSY: JobStatus[] = ["created", "queued", "analyzing", "previewing", "rendering"];

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

/** Upload with progress (fetch can't report upload progress, XHR can). */
export function uploadVideo(file: File, onProgress: (fraction: number) => void): Promise<Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    xhr.open("POST", `${API_URL}/api/jobs`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
      else reject(new Error(body?.detail ?? `Upload failed (${xhr.status})`));
    };
    xhr.onerror = async () => reject(new Error((await diagnoseConnection()) ?? UPLOAD_DROPPED));
    xhr.send(form);
  });
}

const UPLOAD_DROPPED =
  "The server is reachable but dropped the upload. It may have run out of memory or hit an upload size limit; check the backend logs.";

const timeout = (ms: number) => {
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
};

/**
 * Work out *why* the browser can't talk to the backend, since XHR/fetch only
 * report a generic network error. Returns a human-readable cause, or null if
 * the backend looks healthy and reachable from this page.
 */
export async function diagnoseConnection(): Promise<string | null> {
  const here = window.location;
  const api = new URL(API_URL || here.origin, here.href);
  const isLocal = (h: string) => ["localhost", "127.0.0.1", "[::1]"].includes(h);

  if (isLocal(api.hostname) && !isLocal(here.hostname)) {
    return `This site was built without NEXT_PUBLIC_API_URL, so it is calling ${API_URL}. Set it to your backend's URL in your hosting settings and redeploy the frontend.`;
  }
  if (here.protocol === "https:" && api.protocol === "http:") {
    return `The backend URL (${API_URL}) uses http:// but this page is https://, so the browser blocks it. Use the backend's https:// URL in NEXT_PUBLIC_API_URL and redeploy.`;
  }
  const health = `${api.origin}${api.pathname.replace(/\/$/, "")}/api/health`;
  // no-cors succeeds whenever the server answers at all, regardless of CORS.
  try {
    await fetch(health, { mode: "no-cors", cache: "no-store", signal: timeout(20_000) });
  } catch {
    return `Can't reach the backend at ${API_URL}. It may be asleep or still starting (wait a minute and try again), crashed, or the URL is wrong.`;
  }
  // A normal request additionally needs the backend to allow this origin.
  try {
    const res = await fetch(health, { cache: "no-store", signal: timeout(20_000) });
    if (!res.ok) return `The backend at ${API_URL} is up but unhealthy (HTTP ${res.status}). Check its logs.`;
  } catch {
    return `The backend is running but blocks requests from ${here.origin}. Add exactly "${here.origin}" to CORS_ORIGINS on the backend and restart it.`;
  }
  return null;
}

export const getJob = (id: string) => fetch(`${API_URL}/api/jobs/${id}`, { cache: "no-store" }).then(json<Job>);

const post = (id: string, action: "preview" | "render", params: RenderParams) =>
  fetch(`${API_URL}/api/jobs/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  }).then(json<Job>);

export const startPreview = (id: string, p: RenderParams) => post(id, "preview", p);
export const startRender = (id: string, p: RenderParams) => post(id, "render", p);

/** URL for a job file. `v` busts the browser cache when a preview is regenerated. */
export const fileUrl = (id: string, key: string, v?: number) =>
  `${API_URL}/api/jobs/${id}/files/${key}${v ? `?v=${v}` : ""}`;
