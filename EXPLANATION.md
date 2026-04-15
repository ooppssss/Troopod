# Troopod AI – Assignment Brief Explanation
## AI PM Assignment – Landing Page Personalizer

**Live Demo:** https://troopod-bgeo.onrender.com
**GitHub:** [repo link]

---

## 1. How the System Works (Flow)

The system uses a 5-step pipeline to personalize any landing page based on an ad creative.

**Step 1 — Render the Page with Playwright**
When a user submits a URL, we open it in a headless Chromium browser (via Playwright) at 1280×800 viewport. This is critical because modern sites like Decathlon, Myntra, Ajio, etc. are JS-rendered — a simple HTTP request only gets an empty shell. Playwright waits for the page to fully render, then runs JavaScript inside the browser to find every element visible in the viewport (above the fold): headings, buttons, hero sections, and text — along with their real CSS selectors.

**Step 2 — Parse with BeautifulSoup**
The raw viewport elements are organized into a clean structure: headings with selectors, CTA buttons with selectors, and the hero section selector. This gives the AI model precise targeting information instead of vague guesses.

**Step 3 — Analyze the Ad Creative (Vision Model)**
The uploaded ad image is sent to Llama 4 Scout (a multimodal vision model) running on Groq via LangChain. The model returns a structured JSON design spec with exact values: headline text, hex colors, offer text, CTA text, urgency cues, and tone. This is the "brief" that drives personalization.

**Step 4 — Generate Injection Snippet (Code Model)**
The design spec + real page selectors are sent to Llama 3.3 70B on Groq. Instead of rewriting the entire HTML (which breaks pages and exceeds token limits), the model generates a tiny CSS+JS snippet (~1k tokens) that:
- Adds a promotional offer banner at the top
- Swaps the hero headline using the exact CSS selector Playwright found
- Changes CTA button text and color
- Adds urgency messaging
- Adds a "Personalized by Troopod AI" badge

**Step 5 — Inject with BeautifulSoup**
BeautifulSoup inserts the snippet right before </body> in the full, untouched original HTML. The result is the complete original page + targeted CRO enhancements. Nothing is deleted or broken.

---

## 2. Key Components / Agent Design

This is a **two-model pipeline** with specialized tools at each step:

**Playwright (Browser Agent):** Not an LLM — it's a headless browser that renders pages and extracts live DOM elements. This solves the problem of JS-rendered sites that return empty HTML to simple HTTP requests.

**Llama 4 Scout (Vision Model):** Reads the ad image and outputs structured data. Low temperature (0.1) for consistent JSON output. Falls back to safe defaults if JSON parsing fails.

**Llama 3.3 70B (Code Model):** Generates the injection snippet. Gets precise CSS selectors from Playwright (not guessing), so the snippet targets real elements. Low temperature (0.1) for deterministic code output.

**BeautifulSoup (Parser + Injector):** Handles two jobs — organizing Playwright's raw output into clean data, and safely injecting the snippet into the HTML DOM.

**Why the injection approach instead of full HTML rewrite?**
Earlier iterations tried sending the full HTML to the LLM for rewriting. This failed because:
- Groq's free tier has 12k TPM — most pages exceed this
- The LLM would strip sections, break layouts, or build new pages from scratch
- Output was inconsistent between runs

The injection approach sends ~2k tokens to the LLM and preserves the original page perfectly. It's more reliable, faster, and works within free tier limits.

---

## 3. How We Handle Problems

### Random / Unwanted Changes
- The original HTML is never modified by the LLM — it only generates a small addon snippet
- The snippet uses exact CSS selectors from the live browser DOM, not guesses
- Low temperature (0.1) on both models minimizes creative drift
- Even if the snippet has issues, the base page still renders correctly

### Broken UI
- Playwright renders the full page with all CSS/JS before we touch anything
- The injection is appended before </body> — it can't break existing elements
- If the snippet's JS fails to find a selector, it simply doesn't change that element (graceful degradation)
- The "Original" tab loads the live URL directly in an iframe for instant comparison

### Hallucinations
- The vision model outputs structured JSON with specific fields — no room for open-ended hallucination
- If JSON parsing fails, we fall back to safe defaults (generic colors, "Shop Now" CTA)
- The code model receives exact text strings to insert — it's not inventing content
- The ad analysis is shown to the user so they can verify what the model extracted

### Inconsistent Outputs
- Both models run at temperature 0.1 — near-deterministic
- The pipeline is fully deterministic: same ad + same URL = same selectors = same spec = same snippet
- Structured JSON handoff between models eliminates interpretation drift
- Playwright always finds the same elements on the same page

---

## 4. Assumptions Made

1. The landing page is publicly accessible (not behind login/paywall)
2. The ad creative is a static image (PNG, JPG, WebP — not video)
3. The page has standard HTML elements (h1, h2, buttons) that Playwright can detect
4. The user has a free Groq API key (30 seconds to get at console.groq.com)
5. "Personalization" means enhancing the existing page to match the ad — not rebuilding from scratch

---

## 5. What I'd Improve With More Time

- **Multiple variants:** Generate 2-3 CRO options (aggressive vs subtle) for A/B testing
- **Viewport screenshot comparison:** Show actual before/after screenshots side by side
- **Deeper element targeting:** Use Playwright to also extract font families, font sizes, and spacing from the original page for more precise style matching
- **Caching layer:** Cache page renders and ad analyses to skip redundant processing
- **Analytics integration:** Track which personalizations lead to higher engagement
- **Streaming output:** Show the personalized page progressively as the snippet generates