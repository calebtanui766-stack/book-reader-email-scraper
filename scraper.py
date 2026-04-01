import asyncio
import random
import time
import re
import csv
import traceback
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Route

# ====================== CONFIG ======================
RUN_DURATION_MINUTES = 30
TIME_PER_PAGE = 35
MAX_PAGES_PER_SESSION = 60

PROXY_LIST = []  # Leave empty for now

DONATION_KEYWORDS = ["newsletter", "subscribe", "donate", "support", "patreon", "ko-fi", 
                     "buymeacoffee", "tip", "membership", "fan", "reader", "mailing list"]

EMAIL_PATTERN = re.compile(r"""
    \b(?<!\w)
    [A-Za-z0-9._%+-]{1,64}
    @
    [A-Za-z0-9.-]{1,255}
    \.(?![0-9]+\b)
    [A-Za-z]{2,63}
    \b(?! \w)
""", re.VERBOSE | re.IGNORECASE)

def normalize_obfuscated(text: str) -> str:
    if not text: return ""
    replacements = [
        (r'\s*\[at\]\s*|\s*\(at\)\s*|\s+at\s+|\s*#\s*', '@'),
        (r'\s*\[dot\]\s*|\s*\(dot\)\s*|\s+dot\s+|\s*\[\.\]\s*', '.'),
        (r'\s+\.+\s+', '.'),
        (r'(?<!\w)\s*@\s*(?!\w)', '@'),
        (r'(?<!\w)\s*\.\s*(?!\w)', '.'),
    ]
    for pat, repl in replacements:
        text = re.sub(pat, repl, text, flags=re.I)
    return text

STEALTH_INIT_SCRIPT = """
() => {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        const ctx = origGetContext.call(this, type, ...args);
        if (type === '2d') {
            const orig = ctx.getImageData;
            ctx.getImageData = function(...imgArgs) {
                const data = orig.call(this, ...imgArgs);
                for (let i = 0; i < data.data.length; i += 4) {
                    data.data[i] = (data.data[i] + (i % 7)) % 256;
                }
                return data;
            };
        }
        return ctx;
    };
}
"""

async def extract_emails(page: Page, current_url: str):
    # (Same extraction logic as before - kept short for clarity)
    emails = {}
    domain = urlparse(current_url).netloc

    async def block_route(route: Route):
        if route.request.resource_type in {"image", "stylesheet", "font", "media"}:
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route("**/*", block_route)
    except:
        pass

    try:
        text = await page.evaluate("document.body.innerText || ''")
        html = await page.content() if random.random() < 0.2 else ""
        full = text + " " + html
    except:
        full = ""

    norm = normalize_obfuscated(full)
    for m in EMAIL_PATTERN.findall(norm):
        clean = m.lower().strip()
        if "@" in clean:
            emails[clean] = "ultra-regex"

    # ... (keep mailto, footer, JSON-LD parts from previous version)

    final = {}
    for email, src in emails.items():
        if len(email) > 7 and "@" in email:
            dom = email.split("@")[1]
            if not any(bad in dom for bad in ["example.com", "test.com"]):
                ctx = "donation-ready" if any(k in full.lower() for k in DONATION_KEYWORDS) else src
                final[email] = f"{ctx} @ {dom}"
    return final

async def main():
    all_emails = {}
    start_time = time.time()
    end_time = start_time + (RUN_DURATION_MINUTES * 60)

    print(f"🚀 Starting Automatic Reader-Focused Email Extractor v6.3.1")
    print(f"   Duration: {RUN_DURATION_MINUTES} minutes\n")

    async with async_playwright() as p:
        session_count = 0
        while time.time() < end_time:
            session_count += 1
            browser = None
            try:
                browser = await p.chromium.launch(
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled", "--disable-images", "--no-sandbox", "--disable-gpu"]
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 820},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    locale="en-US"
                )
                page = await context.new_page()
                await page.add_init_script(STEALTH_INIT_SCRIPT)

                print(f"Session {session_count}: Visiting reader sites...")

                for url in READER_HUBS:   # Make sure READER_HUBS is defined (from
