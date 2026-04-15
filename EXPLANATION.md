# Troopod AI – Assignment Brief Explanation
## AI PM Assignment – Landing Page Personalizer

---

## 1. How the System Works (Flow)

The system follows a simple 3-step pipeline, orchestrated through LangChain with Groq as the inference backend.

**Step 1 — Fetch the Landing Page**
When the user submits a landing page URL, we use httpx (an async HTTP client) to download the raw HTML of that page. This gives us the actual structure, text, and styling of the existing page.

**Step 2 — Analyze the Ad Creative (Vision Model)**
The uploaded ad image is sent to **Llama 4 Scout** (a multimodal vision model) running on Groq, through LangChain's `ChatGroq` interface. We pass the image as a base64-encoded `image_url` inside a `HumanMessage`. The model extracts: the main headline/offer, visual style and colors, target audience signals, selling points, and tone of voice. This analysis becomes the "brief" that guides personalization.

**Step 3 — Personalize the Page (Text Model)**
The original HTML and the ad analysis are sent to **Llama 3.3 70B** (a strong text model) on Groq, again through LangChain. We use a `SystemMessage` to set the CRO expert persona, and a `HumanMessage` with the HTML + ad analysis + strict rules. The model modifies the existing page following CRO principles: message match, CTA alignment, color consistency, and urgency cues. The modified HTML is returned to the frontend.

**Why two separate models?**
Llama 4 Scout is great at understanding images but lighter on text generation quality. Llama 3.3 70B is much stronger at complex text tasks like rewriting HTML. Using both gives us the best of both worlds at zero cost on Groq's free tier.

---

## 2. Key Components / Agent Design

This is a **two-model pipeline** (not a multi-agent system). Two specialized LLMs handle different parts of the task, connected by a simple data flow.

**Model 1 — Ad Analyst (Llama 4 Scout, vision)**
- Reads the ad image
- Outputs a structured text description of the ad
- Configured with low temperature (0.3) for consistency

**Model 2 — CRO Editor (Llama 3.3 70B, text)**
- Takes the ad description + raw HTML
- Outputs modified HTML with CRO enhancements
- Configured with very low temperature (0.2) for deterministic output

**LangChain's role:**
- Provides clean message abstractions (`HumanMessage`, `SystemMessage`)
- Handles automatic retries (max_retries=2) for Groq rate limits
- Makes it trivial to swap models later (e.g., switch to a bigger model when budget allows)

**Why not a full agent with tools?**
For this scope, a deterministic pipeline is more reliable than an agent that decides what to do. Agents add unpredictability. Our pipeline always does the same 3 things in the same order — fetch, analyze, personalize — which makes debugging easy and output consistent.

---

## 3. How We Handle Problems

### Random / Unwanted Changes
- **Constraint-heavy prompt:** The prompt explicitly says "do NOT build a new page," "keep existing structure," and "only change text, colors, CTAs."
- **System message persona:** The `SystemMessage` reinforces that the model is an enhancer, not a builder.
- **Low temperature (0.2):** Reduces creative drift — the model sticks closer to instructions.

### Broken UI
- **External resources preserved:** All CSS/JS links stay as absolute URLs so they still load.
- **Input cap at 50k chars:** Fits safely within Groq's context window without truncation surprises.
- **Iframe sandbox:** The preview runs in a sandboxed iframe — broken output can't crash the app.
- **Side-by-side toggle:** Users can flip between "Original" and "Personalized" to spot issues.

### Hallucinations
- **No fabrication rule:** The prompt forbids inventing testimonials, fake stats, or placeholder images.
- **Transparent analysis:** The ad analysis is shown to the user so they can verify what the vision model saw. If the analysis is wrong, they know the personalization will be off.
- **Grounded in source:** The model works from actual HTML + actual ad — it's modifying, not inventing.

### Inconsistent Outputs
- **Low temperature on both models:** 0.3 for vision, 0.2 for text — minimal randomness.
- **Deterministic pipeline:** Same input always flows through the same steps in the same order.
- **Checklist-style prompt:** The CRO rules are specific actions (match headline, align CTA), not open-ended.
- **LangChain retries:** If Groq rate-limits us, LangChain retries automatically instead of failing silently.

---

## 4. Assumptions Made

1. The landing page is publicly accessible (not behind login or paywall).
2. The ad creative is a static image (PNG, JPG, WebP — not video or carousel).
3. The page is primarily server-rendered HTML. Heavy SPAs (React apps that render client-side) may not fully personalize since we fetch raw HTML.
4. The user has a free Groq API key (takes 30 seconds to get at console.groq.com).
5. "Personalization" means enhancing the existing page to match the ad — not creating a new page from scratch.

---

## 5. What I'd Improve With More Time

- **Streaming output:** Use LangChain's streaming to show the personalized page progressively as it generates.
- **Screenshot diff:** Use a headless browser to capture before/after screenshots for visual comparison.
- **Multiple variants:** Generate 2-3 CRO options (aggressive vs. subtle) and let the user pick.
- **JS-rendered page support:** Use Playwright to render SPAs before personalizing.
- **Guardrail validation:** Add a post-processing step that checks modified HTML against the original to ensure no sections were deleted.
- **Caching:** Cache fetched pages + ad analyses to avoid re-processing identical inputs.
