import type { Config } from "tailwindcss";

// Colours come from CSS variables (app/globals.css) so light/dark is one source of truth.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        "surface-2": token("surface-2"),
        fill: token("fill"),
        label: token("label"),
        "label-2": token("label-2"),
        "label-3": token("label-3"),
        separator: token("separator"),
        accent: token("accent"),
        success: token("success"),
        warning: token("warning"),
        danger: token("danger"),
      },
    },
  },
  plugins: [],
};

export default config;
