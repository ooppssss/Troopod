# Troopod AI – Landing Page Personalizer

> Upload an ad creative + paste a landing page URL → get a CRO-enhanced, ad-aligned version of that page.
> Powered by **Groq free tier** (Llama 4 Scout + Llama 3.3 70B) via **LangChain**.

---

## Quick Start (5 minutes)

### 1. Get a free Groq API key

Go to [console.groq.com/keys](https://console.groq.com/keys) — no credit card needed.

### 2. Set up your key

```bash
cd backend
cp .env.example .env
# open .env and paste your Groq API key
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the server

```bash
python main.py
```

### 5. Open in browser

Go to **http://localhost:8000** — that's it.

---

## How It Works (System Flow)

```
User uploads ad image + pastes landing page URL
        │
        ▼
┌──────────────────────────┐
│  1. Fetch Page HTML       │  ← httpx grabs the raw HTML from the URL
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  2. Analyze Ad Image      │  ← Llama 4 Scout (vision) via LangChain
│     (Groq + LangChain)   │    reads the ad: headline, offer, colors,
│                           │    tone, audience, selling points
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  3. Personalize HTML      │  ← Llama 3.3 70B (text) via LangChain
│     (Groq + LangChain)   │    rewrites HTML using CRO principles:
│                           │    message match, CTA, colors, urgency
└──────────┬───────────────┘
           │
           ▼
   Personalized HTML returned to frontend
   (preview in iframe, download, or open in new tab)
```

---

## Key Components

| Component | What it does |
|-----------|-------------|
| `backend/main.py` | FastAPI server with 2 LangChain models — vision + text |
| `frontend/index.html` | Single-file UI — upload/link toggle, progress steps, compare view |
| Llama 4 Scout (Groq) | Vision model — reads ad images via LangChain `HumanMessage` |
| Llama 3.3 70B (Groq) | Text model — takes HTML + ad analysis → modified HTML |
| LangChain | Orchestration layer — handles model calls, retries, message formatting |

---

## Why Groq + LangChain?

- **Zero cost:** Groq free tier gives access to all models, no credit card
- **Speed:** Groq's LPU runs Llama 3.3 70B at 200+ tokens/sec
- **Vision built-in:** Llama 4 Scout handles image analysis natively
- **LangChain:** Clean message abstractions, automatic retries, easy model swapping

---

## Groq Free Tier Limits

- ~30 requests/min, ~14,400 requests/day
- All models available (Scout, 70B, etc.)
- If you hit rate limits, the app will show an error — just wait a moment and retry

---

## Deployment (for live demo)

**Render** (recommended):
```bash
# connect GitHub repo, set GROQ_API_KEY as env var
# start command is auto-detected from render.yaml
```

**Quick share with ngrok:**
```bash
ngrok http 8000
```

---

## Tech Stack

- **Backend:** Python, FastAPI, httpx
- **AI Framework:** LangChain (`langchain-groq`)
- **Models:** Llama 4 Scout (vision) + Llama 3.3 70B (text) on Groq
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Cost:** $0 (Groq free tier)
