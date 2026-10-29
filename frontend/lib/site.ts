// Site-wide copy and SEO settings. The FAQ here feeds both the visible FAQ
// section and the FAQPage structured data, so the two can never disagree.

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.clearcorners.tech").replace(/\/+$/, "");
export const SITE_NAME = "Clear Corners";
export const SITE_TITLE = "Remove the Gemini & Veo Watermark from Videos – Clear Corners";
export const SITE_DESCRIPTION =
  "Remove the visible Gemini / Veo logo from AI videos you created. Auto-detects the watermark, previews the result, keeps the original audio. MP4, MOV and WebM.";

export const STEPS = [
  { title: "Upload your video", body: "Drop in an MP4, MOV or WebM up to 200 MB. The watermark is located automatically." },
  { title: "Check the box", body: "The detected logo area is outlined on a frame of your video. Drag or resize it if needed." },
  { title: "Preview, then export", body: "Compare a before/after still and a 3-second clip, then export the full video." },
];

export const METHODS = [
  { title: "Reverse blend", body: "Works out the logo's transparency and colour, then mathematically undoes it. Best quality for most clips." },
  { title: "Temporal fill", body: "Borrows the hidden pixels from neighbouring frames using motion tracking. Great when the scene moves." },
  { title: "Quick fill", body: "Fills the logo area from its surroundings, frame by frame. Fast, and clean on simple backgrounds." },
  { title: "Crop & scale", body: "Trims the corner away and scales back to full size. Always clean, slightly zoomed." },
];

export const FAQ = [
  {
    q: "How do I remove the Veo or Gemini watermark from a video?",
    a: "Upload the video, check that the box covers the logo in the corner, pick a method and generate a preview. If it looks right, export the full video and download it.",
  },
  {
    q: "Does removing the watermark reduce video quality?",
    a: "Only the small logo area is changed. The video keeps its resolution, frame rate and colours, is re-encoded at high quality (H.264, CRF 18), and the original audio is copied untouched.",
  },
  {
    q: "Which method should I choose?",
    a: "Start with Reverse blend. If you still see traces of the logo and the scene behind it moves, try Temporal fill. Quick fill suits plain backgrounds, and Crop & scale is the fallback that always works.",
  },
  {
    q: "Are my videos stored?",
    a: "Uploads, previews and results are deleted automatically one hour after upload.",
  },
  {
    q: "Does this remove SynthID or change whether a video is AI-generated?",
    a: "No. Only the visible logo is removed. Google's invisible SynthID watermark is not touched, and the video is still AI-generated. Use it on videos you created.",
  },
  {
    q: "Which formats and sizes are supported?",
    a: "MP4, MOV and WebM files up to 200 MB. MOV files are exported as MOV; MP4 and WebM are exported as MP4.",
  },
];
