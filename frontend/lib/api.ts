// Thin client for the FastAPI backend.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(form);
  });
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
