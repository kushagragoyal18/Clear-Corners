import type { Metadata, Viewport } from "next";
import "./globals.css";

// Favicon, PNG icon and Apple touch icon come from app/favicon.ico, app/icon.png
// and app/apple-icon.png (Next.js file conventions).
export const metadata: Metadata = {
  title: "Clean Corners – Watermark Remover",
  description: "Remove the visible corner logo from videos you generated with Gemini or Veo.",
  applicationName: "Clean Corners",
  openGraph: {
    title: "Clean Corners – Watermark Remover",
    description: "Remove the visible corner logo from videos you generated with Gemini or Veo.",
    images: [{ url: "/logo.png", width: 512, height: 512, alt: "Clean Corners" }],
  },
  twitter: { card: "summary", images: ["/logo.png"] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
