# Troopod AI – Landing Page Personalizer

> Upload an ad creative + paste a landing page URL → get a CRO-enhanced, ad-aligned version of that page.
> Powered by **Groq free tier** via **LangChain** + **Playwright** viewport scraping + **BeautifulSoup**.

**Live Demo:** [https://troopod-bgeo.onrender.com](https://troopod-bgeo.onrender.com)

---

## Quick Start (Local Development)

### 1. Get a free Groq API key

Go to [console.groq.com/keys](https://console.groq.com/keys) — no credit card needed.

### 2. Set up your key

```bash
cd backend
cp .env.example .env
# paste your Groq API key in .env
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Run the server

```bash
python main.py
```

### 5. Open in browser

Go to **http://localhost:8000**

---

## System Architecture

```
User uploads ad image + pastes landing page URL
        │
        ▼
┌────────────────────────────────────┐
│  1. PLAYWRIGHT (Headless Chrome)    │
│     Opens page in 1280×800 viewport │
│     Waits for JS to render          │
│     Extracts above-the-fold elements│
│     with their real CSS selectors   │
│     Returns full rendered HTML      │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  2. BEAUTIFULSOUP (Parser)          │
│     Organizes viewport elements:    │
│     h1/h2/h3 + selectors           │
│     buttons/CTAs + selectors        │
│     hero/banner section selector    │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  3. LLAMA 4 SCOUT (Vision Model)    │
│     Reads the ad image              │
│     Extracts structured JSON:       │
│     headline, colors, offer, CTA,   │
│     urgency, tone, audience         │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  4. LLAMA 3.3 70B (Code Model)      │
│     Gets: ad spec + real selectors  │
│     Generates: tiny CSS+JS snippet  │
│     (~1k tokens, fits free tier)    │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  5. BEAUTIFULSOUP (Injector)        │
│     Inserts snippet before </body>  │
│     Full original page stays intact │
│     Only above-fold gets enhanced   │
└────────────────────────────────────┘
               │
               ▼
   Personalized HTML → Frontend preview
   (side-by-side compare, download, open in tab)
```

---

## Key Components

| Component | Role |
|-----------|------|
| **Playwright** | Headless Chrome renders the page, scrapes only viewport-visible elements with real CSS selectors |
| **BeautifulSoup** | Parses and organizes extracted elements, cleanly injects the personalization snippet |
| **Llama 4 Scout (Groq)** | Vision model reads ad images, outputs structured JSON design spec |
| **Llama 3.3 70B (Groq)** | Generates a precise CSS+JS injection snippet using the design spec + real selectors |
| **LangChain** | Orchestration layer handling model calls, retries, and message formatting |
| **FastAPI** | Backend server with async endpoints |

---

## Why This Architecture?

| Problem | Our Solution |
|---------|-------------|
| JS-rendered pages (React, Vue) | Playwright renders full page before scraping |
| Blind CSS selectors | Viewport JS finds real selectors from the live DOM |
| LLM rewrites break pages | We inject a small snippet into the untouched original HTML |
| Groq free tier token limits | Snippet approach uses ~2k tokens vs 20k+ for full rewrite |
| Inconsistent colors | Vision model extracts exact hex values from the ad |

---

## Tech Stack

- **Backend:** Python, FastAPI, httpx
- **Scraping:** Playwright (headless Chromium), BeautifulSoup4
- **AI Framework:** LangChain (`langchain-groq`)
- **Models:** Llama 4 Scout (vision) + Llama 3.3 70B (text) on Groq
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Deployment:** Docker on Render
- **Cost:** $0 (Groq free tier)