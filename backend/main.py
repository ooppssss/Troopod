"""
Troopod AI Landing Page Personalizer
Pipeline: Playwright (viewport scrape) → BS4 (parse) → Scout (ad spec) → LLM (snippet) → Inject
"""

import os
import re
import json
import base64
import asyncio
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from bs4 import BeautifulSoup, Comment

# langchain imports
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()


# ---------- app setup ----------

app = FastAPI(title="Troopod AI Page Personalizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- models ---
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
CODE_MODEL = "llama-3.3-70b-versatile"

llm_vision = ChatGroq(
    model=VISION_MODEL,
    api_key=GROQ_API_KEY,
    temperature=0.1,
    max_tokens=800,
    max_retries=2,
)

llm_code = ChatGroq(
    model=CODE_MODEL,
    api_key=GROQ_API_KEY,
    temperature=0.1,
    max_tokens=3000,
    max_retries=2,
)


# =============================================
# STEP 1: PLAYWRIGHT — SCRAPE ONLY THE VIEWPORT
# =============================================

async def fetch_page_with_viewport(url: str) -> tuple[str, str, list]:
    """
    opens page in headless browser, waits for render, then:
    - grabs the FULL page html (for final injection)
    - takes a viewport screenshot (for visual reference)
    - extracts only above-the-fold elements via JS
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # launch headless chromium
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        # go to the url, wait for network to settle
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            # fallback: just wait for dom
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # small pause for lazy-loaded content
        await asyncio.sleep(2)

        # grab full page html (we inject into this later)
        full_html = await page.content()

        # take viewport screenshot as base64 (optional: for debugging)
        screenshot_bytes = await page.screenshot(type="png")
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        # --- THE KEY PART: extract only above-the-fold elements ---
        viewport_elements = await page.evaluate("""
            () => {
                const results = [];
                const viewportHeight = window.innerHeight;

                // grab all visible elements in the viewport
                const allElements = document.querySelectorAll(
                    'h1, h2, h3, p, a, button, img, span, div, section, header, nav'
                );

                for (const el of allElements) {
                    const rect = el.getBoundingClientRect();

                    // skip elements not in viewport
                    if (rect.top > viewportHeight || rect.bottom < 0) continue;
                    // skip invisible elements
                    if (rect.width === 0 || rect.height === 0) continue;

                    const tag = el.tagName.toLowerCase();
                    const text = el.innerText?.trim().substring(0, 100) || '';
                    const id = el.id || '';
                    const classes = Array.from(el.classList).slice(0, 3).join('.');

                    // build a usable CSS selector
                    let selector = tag;
                    if (id) selector = '#' + id;
                    else if (classes) selector = tag + '.' + classes;

                    // only keep meaningful elements
                    const isHeading = ['h1','h2','h3'].includes(tag);
                    const isButton = tag === 'button' || (tag === 'a' && (
                        classes.includes('btn') || classes.includes('cta') ||
                        classes.includes('button') || classes.includes('action')
                    ));
                    const isImage = tag === 'img';
                    const isHero = classes.includes('hero') || classes.includes('banner') ||
                                   classes.includes('jumbotron') || id.includes('hero');
                    const isNav = tag === 'nav' || classes.includes('nav');
                    const hasText = text.length > 2;

                    if (isHeading || isButton || isImage || isHero || isNav || (tag === 'p' && hasText)) {
                        results.push({
                            tag: tag,
                            text: text,
                            selector: selector,
                            type: isHeading ? 'heading' :
                                  isButton ? 'button' :
                                  isImage ? 'image' :
                                  isHero ? 'hero' :
                                  isNav ? 'nav' : 'text',
                            src: tag === 'img' ? (el.src || '').substring(0, 200) : '',
                            top: Math.round(rect.top),
                        });
                    }
                }

                // sort by position (top to bottom)
                results.sort((a, b) => a.top - b.top);
                // limit to avoid bloat
                return results.slice(0, 20);
            }
        """)

        await browser.close()

    return full_html, screenshot_b64, viewport_elements


# =============================================
# STEP 2: PARSE VIEWPORT ELEMENTS WITH BS4
# =============================================

def organize_viewport_data(viewport_elements: list) -> dict:
    """organize the raw viewport elements into structured page info"""

    headings = []
    buttons = []
    hero_selector = None
    images = []
    nav_items = []

    for el in viewport_elements:
        if el["type"] == "heading":
            headings.append({
                "tag": el["tag"],
                "text": el["text"],
                "selector": el["selector"],
            })

        elif el["type"] == "button":
            buttons.append({
                "text": el["text"],
                "selector": el["selector"],
            })

        elif el["type"] == "hero" and not hero_selector:
            hero_selector = el["selector"]

        elif el["type"] == "image" and el.get("src"):
            images.append({
                "selector": el["selector"],
                "src": el["src"][:100],
            })

        elif el["type"] == "nav":
            nav_items.append(el["selector"])

    return {
        "headings": headings[:5],
        "buttons": buttons[:4],
        "hero_selector": hero_selector,
        "images": images[:3],
        "nav_selectors": nav_items[:2],
        "total_viewport_elements": len(viewport_elements),
    }


# =============================================
# STEP 3: EXTRACT DESIGN SPEC FROM AD
# =============================================

async def extract_design_spec(image_bytes: bytes, media_type: str) -> dict:
    """vision model reads ad image → structured JSON design spec"""
    b64 = base64.b64encode(image_bytes).decode()

    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64}"},
            },
            {
                "type": "text",
                "text": """Analyze this ad and return ONLY a JSON object:
{
  "headline": "main headline from the ad",
  "sub_headline": "secondary text or tagline",
  "cta_text": "call to action text",
  "offer": "the deal (e.g. 60% off)",
  "primary_color": "#hex dominant color",
  "accent_color": "#hex highlight/button color",
  "text_color": "#hex main text color",
  "tone": "one word: urgent/premium/friendly/bold",
  "urgency": "time-limited element if any"
}
ONLY valid JSON. No markdown.""",
            },
        ]
    )

    response = await asyncio.to_thread(llm_vision.invoke, [message])
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "headline": "Special Offer",
            "sub_headline": "",
            "cta_text": "Shop Now",
            "offer": "",
            "primary_color": "#e63946",
            "accent_color": "#ff6b35",
            "text_color": "#ffffff",
            "tone": "bold",
            "urgency": "",
        }


# =============================================
# STEP 4: GENERATE INJECTION SNIPPET
# =============================================

async def generate_injection_snippet(design_spec: dict, page_info: dict) -> str:
    """LLM generates CSS+JS using ad spec + real viewport selectors"""

    system_msg = SystemMessage(
        content="You write small CSS+JS snippets that personalize web pages. Output ONLY code inside a <div>, no explanation."
    )

    user_msg = HumanMessage(
        content=f"""Generate an HTML snippet to personalize a landing page.

AD SPEC: {json.dumps(design_spec)}

ABOVE-THE-FOLD ELEMENTS FOUND ON PAGE:
Headings: {json.dumps(page_info.get('headings', []))}
Buttons: {json.dumps(page_info.get('buttons', []))}
Hero: {page_info.get('hero_selector', 'not found')}

Create a <div> with:
1. <style>: fixed top banner (z-index:99999, bg:{design_spec.get('accent_color','#ff6b35')}, white text, 50px tall), body margin-top:55px!important, bottom-right badge (fixed, small, opacity:0.8)
2. Offer banner div: "{design_spec.get('offer','')}" + "{design_spec.get('urgency','')}"
3. <script> on DOMContentLoaded:
   - h1 selectors {json.dumps([h['selector'] for h in page_info.get('headings',[]) if h['tag']=='h1'])} → text: "{design_spec.get('headline','')}"
   - h2 selectors {json.dumps([h['selector'] for h in page_info.get('headings',[]) if h['tag']=='h2'])} → text: "{design_spec.get('sub_headline','')}"
   - button selectors {json.dumps([b['selector'] for b in page_info.get('buttons',[])])} → first one text: "{design_spec.get('cta_text','Shop Now')}", bg: {design_spec.get('accent_color','#ff6b35')}
4. Badge div: "Personalized by Troopod AI"

Return ONLY <div>...</div>. No markdown."""
    )

    response = await asyncio.to_thread(llm_code.invoke, [system_msg, user_msg])
    result = response.content.strip()

    if result.startswith("```"):
        result = result.split("\n", 1)[1]
    if result.endswith("```"):
        result = result.rsplit("```", 1)[0]

    return result.strip()


# =============================================
# STEP 5: INJECT INTO FULL HTML WITH BS4
# =============================================

def inject_snippet(original_html: str, snippet: str) -> str:
    """BS4 cleanly inserts the snippet before </body>"""
    soup = BeautifulSoup(original_html, "html.parser")
    snippet_tag = BeautifulSoup(snippet, "html.parser")

    body = soup.find("body")
    if body:
        body.append(Comment(" Troopod AI Personalization "))
        body.append(snippet_tag)
    else:
        soup.append(snippet_tag)

    return str(soup)


# =============================================
# MAIN ROUTE
# =============================================

@app.post("/api/personalize")
async def personalize_page(
    landing_page_url: str = Form(...),
    ad_image: UploadFile = File(None),
    ad_link: str = Form(None),
):
    """main endpoint — ad + url → personalized html"""

    if not ad_image and not ad_link:
        raise HTTPException(status_code=400, detail="Please provide an ad image or ad link.")

    # get ad image bytes
    if ad_image:
        image_bytes = await ad_image.read()
        media_type = ad_image.content_type or "image/png"
    elif ad_link:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(ad_link)
                resp.raise_for_status()
                image_bytes = resp.content
                media_type = resp.headers.get("content-type", "image/png").split(";")[0]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Couldn't download ad image: {str(e)}")

    # step 1: playwright renders page, gets full html + viewport elements
    try:
        full_html, screenshot_b64, viewport_elements = await fetch_page_with_viewport(landing_page_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't load that page: {str(e)}")

    # step 2: organize viewport data with BS4 logic
    page_info = organize_viewport_data(viewport_elements)

    # step 3: extract design spec from ad (vision model)
    try:
        design_spec = await extract_design_spec(image_bytes, media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ad analysis failed: {str(e)}")

    # gap for TPM
    await asyncio.sleep(3)

    # step 4: generate injection snippet (code model)
    try:
        snippet = await generate_injection_snippet(design_spec, page_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Snippet generation failed: {str(e)}")

    # step 5: inject into full html
    personalized_html = inject_snippet(full_html, snippet)

    return {
        "status": "success",
        "ad_analysis": json.dumps(design_spec, indent=2),
        "personalized_html": personalized_html,
        "original_url": landing_page_url,
        "viewport_elements_found": len(viewport_elements),
        "page_info": page_info,
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "vision_model": VISION_MODEL,
        "code_model": CODE_MODEL,
        "scraper": "playwright + beautifulsoup4",
    }


# serve frontend
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)