export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Plus Jakarta Sans'", "'Segoe UI'", "sans-serif"],
        body: ["'Inter'", "'Segoe UI'", "sans-serif"],
      },
      colors: {
        ink:    "#0b1f3a",
        ocean:  "#0b7285",
        teal:   "#00b4a6",
        mint:   "#b8f2e6",
        sand:   "#f8f5f0",
        ember:  "#f97316",
        // Extended palette from logo
        "brand-blue":  "#1a3a6b",
        "brand-teal":  "#00b4a6",
        "brand-green": "#27ae60",
        "brand-gold":  "#f5a623",
      },
      boxShadow: {
        panel:  "0 8px 32px rgba(11,31,58,0.10), 0 2px 8px rgba(11,31,58,0.06)",
        card:   "0 2px 12px rgba(11,31,58,0.08)",
        "card-lg": "0 16px 40px rgba(11,31,58,0.12)",
        "teal": "0 4px 16px rgba(0,180,166,0.28)",
        "inner-teal": "inset 0 1px 0 rgba(0,180,166,0.15)",
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(145deg, #0b1f3a 0%, #0b5266 60%, #0b7285 100%)",
        "teal-gradient":  "linear-gradient(135deg, #00b4a6 0%, #0b7285 100%)",
        "card-gradient":  "linear-gradient(160deg, rgba(255,255,255,0.95) 0%, rgba(240,247,249,0.95) 100%)",
      },
      animation: {
        "fade-in":    "fadeInUp 0.35s ease forwards",
        "slide-in":   "slideIn 0.3s ease forwards",
        "pulse-soft": "pulse-dot 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
