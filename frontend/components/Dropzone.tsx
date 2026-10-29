"use client";

import { useRef, useState } from "react";
import { Icon } from "./ui";

const ACCEPT = [".mp4", ".mov", ".webm"];
const MAX_BYTES = 200 * 1024 * 1024;

export function validateFile(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ACCEPT.includes(ext)) return "That file type isn't supported. Choose an MP4, MOV or WebM video.";
  if (file.size > MAX_BYTES) return "That video is larger than 200 MB. Trim it or export a smaller version.";
  return null;
}

export default function Dropzone({ onFile }: { onFile: (f: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0); // dragenter/leave fire for children too

  const pick = (files: FileList | null) => {
    if (files && files[0]) onFile(files[0]);
  };

  return (
    <button
      type="button"
      onClick={() => input.current?.click()}
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current++;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        if (--depth.current <= 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        pick(e.dataTransfer.files);
      }}
      className={`pressable group card relative flex w-full flex-col items-center justify-center gap-4 px-6 py-14 text-center outline-none
        focus-visible:ring-4 focus-visible:ring-accent/30 sm:py-20
        ${over ? "!ring-2 !ring-accent bg-accent/[0.04]" : "hover:bg-surface/80"}`}
    >
      <span
        className={`flex h-16 w-16 items-center justify-center rounded-[1.25rem] bg-accent/10 text-accent transition-transform duration-200 ease-out
          ${over ? "-translate-y-1 scale-110" : "group-hover:-translate-y-0.5"}`}
      >
        {Icon.upload("h-8 w-8")}
      </span>
      <span>
        <span className="t-title block">{over ? "Drop to upload" : "Drop a video, or click to browse"}</span>
        <span className="mt-1 block text-[0.9375rem] text-label-2">MP4, MOV or WebM, up to 200 MB</span>
      </span>
      <input
        ref={input}
        type="file"
        accept={ACCEPT.join(",")}
        className="hidden"
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
      />
    </button>
  );
}
