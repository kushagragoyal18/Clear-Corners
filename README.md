# Watermark Remover

Removes the **visible** corner logo that Gemini / Veo overlays on generated videos.

> For use on videos you created. Removing the visible mark doesn't change the video's AI-generated status.

Out of scope, by design: the invisible SynthID watermark is never detected, targeted or deliberately degraded, and
the app doesn't strip provenance metadata. (See [Known limitations](#known-limitations) for what re-encoding
means for C2PA.)

```
.
├── docker-compose.yml
├── backend/                   FastAPI + OpenCV + NumPy + FFmpeg
│   ├── app/
│   │   ├── main.py            HTTP API (upload, status, preview, render, files)
│   │   ├── config.py          env-driven settings (size limit, TTL, workers…)
│   │   ├── jobs.py            JobStore + TaskQueue interfaces, in-process impls, TTL cleaner
│   │   ├── tasks.py           analyse / preview / render tasks (RQ-compatible signatures)
│   │   └── video/
│   │       ├── detection.py   watermark localisation + per-pixel logo mask
│   │       ├── alpha.py       Mode A: alpha/colour estimation + reverse blending
│   │       ├── inpaint.py     Mode B: Telea + optical-flow temporal inpainting
│   │       ├── crop.py        Mode C: crop-and-rescale
│   │       ├── ffmpeg_io.py   ffprobe, raw-frame pipe reader/writer
│   │       └── pipeline.py    sampling, per-mode processors, streaming render
│   └── tests/                 synthetic-video tests (alpha maths/PSNR, detection, inpaint, API)
└── frontend/                  Next.js 14 + React + TypeScript + Tailwind
    ├── app/page.tsx           upload → adjust box → preview → render → download
    ├── components/            Dropzone, BoxEditor, ModeSelector, BeforeAfterSlider, ProgressBar
    └── lib/api.ts             typed API client (XHR upload with progress, polling helpers)
```

## Running

### Docker (recommended)

```bash
docker compose up --build
```

Then open http://localhost:3000. The API is at http://localhost:8000 (`/docs` for OpenAPI).

### Local development

Requirements: Python 3.11+, Node 20+, and `ffmpeg`/`ffprobe` on `PATH`.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev            # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
```

Tests (no FFmpeg needed; everything runs on synthetic NumPy videos):

```bash
cd backend && python -m pytest -s
```

### Deploying to DigitalOcean

`docker-compose.prod.yml` runs three services on one domain:
- **Caddy:** handles HTTPS and routes `/api/*` to the backend and everything else to the frontend.
- **Frontend:** built with an empty `NEXT_PUBLIC_API_URL`, so it calls `/api/...` on its own domain and CORS doesn't come into play.
- **Backend:** reachable only through Caddy.

1. **Create a Droplet.** Use Ubuntu 24.04 with at least 2 vCPU and 4 GB RAM; video processing is CPU-heavy. Add your SSH key.
2. **Point DNS at the Droplet.** Create an `A` record for your domain with the Droplet's IP, at your registrar or under DigitalOcean → Networking → Domains.
3. **Open the firewall.** Allow ports 22, 80 and 443, either with a DigitalOcean Cloud Firewall or with `ufw` on the server.
4. **Upload the code** from your PC (Git Bash). This skips the local dependency folders:
   ```bash
   tar --exclude=node_modules --exclude=.venv --exclude=.next --exclude=data -czf wr.tgz watermark-remover
   ```
   ```bash
   scp wr.tgz root@YOUR_DROPLET_IP:/opt/
   ```
   Alternatively, push the project to a private GitHub repo and `git clone` it on the server.
5. **Install Docker and start the stack** on the server (`ssh root@YOUR_DROPLET_IP`):
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
   ```bash
   cd /opt && tar -xzf wr.tgz && cd watermark-remover
   ```
   ```bash
   echo "DOMAIN=yourdomain.com" > .env
   ```
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
6. **Open `https://yourdomain.com`.** Caddy issues the certificate on the first request, which can take up to a minute. To watch the logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f
   ```

**To update**, upload the new code and run the same `up -d --build` command again. Job files and certificates live in Docker volumes, so they survive rebuilds.

**Notes**
- **Small Droplets:** on 1–2 GB of RAM, the frontend build can run out of memory. Add swap first: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`.
- **Cloudflare:** the free plan's proxy rejects uploads over 100 MB. Use DNS-only mode (grey cloud) for this domain.
- **No login or rate limiting:** anyone with the URL can use the server's CPU. `WORKERS` is set to 1 to cap concurrent jobs. Consider adding basic auth in the `Caddyfile` if the site is private.

### Configuration (backend env vars)

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATA_DIR` | `./data` | Where job folders (upload, previews, output) live |
| `MAX_UPLOAD_MB` | `200` | Upload size limit |
| `JOB_TTL_SECONDS` | `3600` | Job folders are deleted this long after upload |
| `CLEANUP_INTERVAL_SECONDS` | `300` | How often the cleaner runs |
| `WORKERS` | `2` | Concurrent background tasks |
| `PREVIEW_SECONDS` | `3` | Length of the preview clip |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list |

## Workflow

1. **Upload** (MP4/MOV/WebM, ≤ 200 MB). The extension and size are checked in the browser and again on the server
   while the upload streams to disk.
2. **Analyse.** `ffprobe` reads the stream parameters. About 40 evenly spaced frames are decoded at ≤ 640 px and the
   watermark box is detected. A full-resolution frame from the middle of the video is saved for the box editor.
3. **Adjust.** The detected box is drawn on that frame. You can drag or resize it, pick a mode and toggle high
   quality.
4. **Preview.** A 3-second clip from the middle of the video is rendered with the real pipeline, and its middle frame
   becomes the before/after still. Full render stays disabled until a preview exists for the current box and mode.
5. **Render and download.** The full video is rendered. Progress is polled once a second.

All of a job's files are deleted one hour after upload.

## How it works

### Watermark localisation (`video/detection.py`)

A visible overlay is static: it stays on the same pixels while the content underneath moves. Two cues are computed
over the sampled frames:

* **Persistent edges.** Take the gradient magnitude of the temporal *median* frame and divide it by the mean
  per-frame gradient magnitude. The result is about 1 for edges present in every frame and small for moving edges.
  The logo's outline survives the median; moving content washes out.
* **Low temporal variance.** Under an overlay of opacity α, background variance shrinks by (1−α)², so the logo is
  quieter than its surroundings.

The combined score map is searched in each corner (30 % × 30 % regions):

1. Otsu threshold.
2. Morphological closing, so separate glyphs (such as a sparkle plus a wordmark) merge.
3. Connected components. A blob is rejected if it spans most of the region or is a long thin line.

Confidence is the winning blob's contrast against both its corner and the frame as a whole. Bottom-right gets a mild
prior. Nothing is pixel-hard-coded. When confidence is low, the app falls back to a box proportional to the frame
size and flags it in the UI as "please adjust".

Once a box is chosen (detected or user-edited), `logo_mask` builds a per-pixel mask inside it. It recomputes the
score at full resolution on about 48 crops, fills holes so outlined glyphs become solid, adds the variance-drop cue,
and dilates the result.

### Mode A — reverse alpha blending (`video/alpha.py`)

Compositing model, with α and L constant over time:

    I_t = (1 − α)·B_t + α·L

* **Background estimate.** Each sampled crop is Telea-inpainted under the mask to get B̂_t.
* **Stage 1, per pixel across frames.** Regress I on B̂ with one slope shared across channels:
  slope = 1 − α, intercept = α·L. This only works where the background *varies*. At pixels where it varies enough
  and α is moderate, intercept/α gives the logo colour. The robust median across those pixels is the global L.
  If no pixel qualifies, L defaults to white.
* **Stage 2, L fixed.** Closed form per pixel:
  α = Σ w (I − B̂)(L − B̂) / Σ w (L − B̂)².
  This is much less affected by errors in B̂ than the stage-1 slope, which suffers regression dilution.
* **Stage 3.** Re-solve L by least squares given α. Stages 2 and 3 alternate three times.
* **Frame weights.** Frames whose ring around the logo is smooth get more weight, because inpainting is accurate
  there.
* **Recovery.** `B = (I − α·L) / (1 − α)`, clamped to [0, 255]. Where α ≥ 0.85 the division would blow up noise, so
  those pixels (slightly dilated) are Telea-inpainted instead (Mode B fallback).

Synthetic test result (`tests/test_alpha.py`): masked-region PSNR goes from **11.6 dB → 36.5 dB** with a blind
estimate. With the true background, α is recovered to within 8-bit rounding error.

### Mode B — inpainting (`video/inpaint.py`)

* **Fast.** Per-frame `cv2.inpaint(..., INPAINT_TELEA)` on the dilated mask, applied only to the region around the
  logo.
* **Temporal.** For each frame t, Farneback optical flow is computed from t to each of the ±2 neighbouring frames:
  1. The flow inside the mask is unreliable, because the static logo pulls it towards zero. It is replaced by a
     normalised-convolution extrapolation of the surrounding flow.
  2. Each neighbour is warped into t's geometry. Only pixels that came from *unmasked* areas of the neighbour count.
  3. Each warp is checked on the visible ring around the logo. Misaligned neighbours (large or complex motion) are
     down-weighted or dropped.
  4. The remaining candidates are blended, weighted by temporal distance and warp quality. Whatever no neighbour
     could see is Telea-filled.
  5. A light motion-compensated blend with the previous output (feathered, mask only) reduces flicker.

  On a synthetic panning scene, temporal inpainting beats spatial by about 3.5 dB in the masked area.

### Mode C — crop and scale (`video/crop.py`)

Removes the horizontal or vertical band containing the logo, whichever keeps more area. It then crops the other axis
back to the original aspect ratio and resizes to the original resolution with Lanczos. This always gives a clean
result, at the cost of a slight zoom.

### Encoding (`video/ffmpeg_io.py`)

* **Decode.** `ffmpeg … -f rawvideo -pix_fmt bgr24 -` piped to NumPy. Sampling uses ffmpeg's own
  `fps`/`crop`/`scale` filters, so only the needed pixels cross the pipe.
* **Encode.** Raw BGR goes to ffmpeg's stdin, with the original file as a second input:
  * Video: `-map 0:v:0`, `libx264 -crf 18 -preset veryfast` (`slow` with "high quality").
  * Audio: `-map 1:a? -c:a copy`.
  * Metadata: `-map_metadata 1`.
* **Stream parameters.** Resolution, exact rational frame rate, pixel format (when libx264 supports it, otherwise
  `yuv420p`) and colour tags (primaries/trc/matrix/range) match the source.
* **Containers.** MOV stays MOV. MP4 and WebM become MP4, because H.264 isn't valid in WebM. Audio is stream-copied
  unless the codec can't live in MP4 (for example Vorbis), in which case it is re-encoded to AAC.
* **No temp images.** No intermediate image files are written.

### Job queue (`jobs.py`, `tasks.py`)

* **`TaskQueue.enqueue(func_path, *json_args)`** is implemented by a thread pool today. OpenCV and ffmpeg release
  the GIL, so threads work well here. The call has the same shape as `rq.Queue.enqueue("app.tasks.run_render",
  job_id, params)`.
* **`JobStore`** is implemented by `FileJobStore`, which keeps one atomic JSON file per job inside the job's
  directory. A separate worker process sharing the volume can already use it.
* **Moving to Redis/RQ** means swapping `InProcessQueue` for an RQ adapter, optionally adding a Redis-backed store,
  and running `rq worker` with the same image.
* **Cleanup.** A daemon thread deletes job folders older than `JOB_TTL_SECONDS`.

## Known limitations

* **Busy backgrounds and fast motion behind the logo are hardest.**
  * Mode A needs a usable background estimate. Fine texture under the logo makes B̂ inaccurate, which biases α.
  * Temporal inpainting relies on optical flow. Fast, non-rigid or occluding motion breaks the warp check and drops
    back to spatial fill, which smears detail.
  * A static camera on a static scene gives temporal inpainting nothing to borrow.
* **Detection assumes a static overlay in a corner.** Logos that animate, move or fade in won't be found, and an
  almost static video gives weak cues. In both cases adjust the box by hand.
* **Mode A assumes one logo colour and a fixed opacity.** Logos with gradients or drop shadows are only approximated.
  Their residue is usually faint; switch to temporal inpainting if it bothers you.
* **Variable frame rate** sources are re-timed to their average rate.
* **C2PA / content credentials.** Re-encoding creates a new file. FFmpeg carries over container metadata tags but not
  the embedded C2PA manifest box. Any manifest would also no longer validate, because it is bound to the original
  bytes. The app doesn't try to remove it. If you need provenance on the output, sign it as a derived asset with the
  original as an ingredient (for example with `c2patool`).
* **SynthID** is untouched by design. Re-encoding at CRF 18 isn't aimed at it. The output is still an AI-generated
  video, and it should be presented as one.
* Upload, preview and render each hold one job's frames in memory: a window of 5 full frames plus small regions of
  interest. Very high resolutions (8K) will need more RAM.
