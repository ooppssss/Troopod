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

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

app = FastAPI(title="Troopod AI Page Personalizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
CODE_MODEL = "llama-3.3-70b-versatile"

llm_vision = ChatGroq(
    model=VISION_MODEL, api_key=GROQ_API_KEY,
    temperature=0.1, max_tokens=800, max_retries=2,
)

llm_code = ChatGroq(
    model=CODE_MODEL, api_key=GROQ_API_KEY,
    temperature=0.1, max_tokens=3000, max_retries=2,
)


# =============================================
# STEP 1: PLAYWRIGHT — RENDER PAGE + SCRAPE VIEWPORT
# =============================================

async def fetch_page_with_viewport(url: str) -> tuple[str, list]:
    """open page in headless chrome, grab full html + above-the-fold elements"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # let lazy content load
        await asyncio.sleep(2)

        # grab full rendered html
        full_html = await page.content()

        # extract only elements visible in the viewport (above the fold)
        viewport_elements = await page.evaluate("""
            () => {
                const results = [];
                const vh = window.innerHeight;

                const els = document.querySelectorAll(
                    'h1, h2, h3, p, a, button, img, section, header, nav'
                );

                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    if (r.top > vh || r.bottom < 0 || r.width === 0 || r.height === 0) continue;

                    const tag = el.tagName.toLowerCase();
                    const text = (el.innerText || '').trim().substring(0, 100);
                    const id = el.id || '';
                    const cls = Array.from(el.classList).slice(0, 3).join('.');

                    let sel = tag;
                    if (id) sel = '#' + id;
                    else if (cls) sel = tag + '.' + cls;

                    const isHeading = ['h1','h2','h3'].includes(tag);
                    const isButton = tag === 'button' || (tag === 'a' && (
                        cls.includes('btn') || cls.includes('cta') || cls.includes('button')
                    ));
                    const isHero = cls.includes('hero') || cls.includes('banner') || id.includes('hero');

                    if (isHeading || isButton || isHero || (tag === 'p' && text.length > 5)) {
                        results.push({ tag, text, selector: sel,
                            type: isHeading ? 'heading' : isButton ? 'button' : isHero ? 'hero' : 'text',
                            top: Math.round(r.top)
                        });
                    }
                }
                results.sort((a, b) => a.top - b.top);
                return results.slice(0, 20);
            }
        """)

        await browser.close()

    return full_html, viewport_elements


# =============================================
# STEP 2: ORGANIZE VIEWPORT DATA
# =============================================

def organize_viewport_data(elements: list) -> dict:
    """structure the raw viewport elements"""
    headings, buttons, hero = [], [], None

    for el in elements:
        if el["type"] == "heading":
            headings.append({"tag": el["tag"], "text": el["text"], "selector": el["selector"]})
        elif el["type"] == "button":
            buttons.append({"text": el["text"], "selector": el["selector"]})
        elif el["type"] == "hero" and not hero:
            hero = el["selector"]

    return {
        "headings": headings[:5],
        "buttons": buttons[:4],
        "hero_selector": hero,
    }


# =============================================
# STEP 3: EXTRACT AD DESIGN SPEC
# =============================================

async def extract_design_spec(image_bytes: bytes, media_type: str) -> dict:
    """vision model reads ad → JSON spec"""
    b64 = base64.b64encode(image_bytes).decode()

    message = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
        {"type": "text", "text": """Analyze this ad and return ONLY a JSON object:
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
ONLY valid JSON. No markdown."""},
    ])

    response = await asyncio.to_thread(llm_vision.invoke, [message])
    raw = response.content.strip()

    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"): raw = raw.rsplit("```", 1)[0]

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "headline": "Special Offer", "sub_headline": "", "cta_text": "Shop Now",
            "offer": "", "primary_color": "#e63946", "accent_color": "#ff6b35",
            "text_color": "#ffffff", "tone": "bold", "urgency": "",
        }


# =============================================
# STEP 4: GENERATE INJECTION SNIPPET
# =============================================

async def generate_injection_snippet(spec: dict, info: dict) -> str:
    """LLM generates CSS+JS snippet using ad spec + real viewport selectors"""

    system_msg = SystemMessage(
        content="You write small CSS+JS snippets that personalize web pages. Output ONLY code inside a <div>, no explanation."
    )

    user_msg = HumanMessage(content=f"""Generate an HTML snippet to personalize a landing page.

AD SPEC: {json.dumps(spec)}

ABOVE-THE-FOLD ELEMENTS (from real browser viewport):
Headings: {json.dumps(info.get('headings', []))}
Buttons: {json.dumps(info.get('buttons', []))}
Hero: {info.get('hero_selector', 'not found')}

Create a <div> with:
1. <style>: fixed top banner (z-index:99999, bg:{spec.get('accent_color','#ff6b35')}, white bold text, 50px, centered), body margin-top:55px!important, bottom-right badge (fixed, small, opacity:0.8)
2. Offer banner div: "{spec.get('offer','')}" + "{spec.get('urgency','')}"
3. <script> on DOMContentLoaded:
   - h1 selectors {json.dumps([h['selector'] for h in info.get('headings',[]) if h['tag']=='h1'])} → text: "{spec.get('headline','')}"
   - h2 selectors {json.dumps([h['selector'] for h in info.get('headings',[]) if h['tag']=='h2'])} → text: "{spec.get('sub_headline','')}"
   - button selectors {json.dumps([b['selector'] for b in info.get('buttons',[])])} → first one text: "{spec.get('cta_text','Shop Now')}", bg: {spec.get('accent_color','#ff6b35')}
4. Badge: "Personalized by Troopod AI"

Return ONLY <div>...</div>. No markdown.""")

    response = await asyncio.to_thread(llm_code.invoke, [system_msg, user_msg])
    result = response.content.strip()

    if result.startswith("```"): result = result.split("\n", 1)[1]
    if result.endswith("```"): result = result.rsplit("```", 1)[0]

    return result.strip()


# =============================================
# STEP 5: INJECT WITH BS4
# =============================================

def inject_snippet(html: str, snippet: str) -> str:
    """insert personalization snippet before </body>"""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if body:
        body.append(Comment(" Troopod AI Personalization "))
        body.append(BeautifulSoup(snippet, "html.parser"))
    else:
        soup.append(BeautifulSoup(snippet, "html.parser"))
    return str(soup)


# =============================================
# ROUTES
# =============================================

@app.post("/api/personalize")
async def personalize_page(
    landing_page_url: str = Form(...),
    ad_image: UploadFile = File(None),
    ad_link: str = Form(None),
):
    if not ad_image and not ad_link:
        raise HTTPException(status_code=400, detail="Please provide an ad image or ad link.")

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

    # step 1: playwright renders page + scrapes viewport
    try:
        full_html, viewport_elements = await fetch_page_with_viewport(landing_page_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't load that page: {str(e)}")

    # step 2: organize viewport data
    page_info = organize_viewport_data(viewport_elements)

    # step 3: extract ad spec
    try:
        design_spec = await extract_design_spec(image_bytes, media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ad analysis failed: {str(e)}")

    await asyncio.sleep(3)

    # step 4: generate snippet
    try:
        snippet = await generate_injection_snippet(design_spec, page_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Snippet generation failed: {str(e)}")

    # step 5: inject
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
    return {"status": "ok", "vision": VISION_MODEL, "code": CODE_MODEL, "scraper": "playwright"}


app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)