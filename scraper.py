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
    if not text:
        return ""
    replacements = [
        (r'\s*\[at\]\s*|\s*\(at\]\s*|\s+at\s+|\s*#\s*', '@'),
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
    emails = {}
    domain = urlparse(current_url).netloc

    # Block unnecessary resources to speed up and reduce detection
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

    # Normalize obfuscated emails
    norm = normalize_obfuscated(full)

    # Extract emails using regex
    for m in EMAIL_PATTERN.findall(norm):
        clean = m.lower().strip()
        if "@" in clean and len(clean) > 7:
            emails[clean] = "ultra-regex"

    # Additional simple extraction for mailto: links (basic version)
    try:
        mailtos = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href^="mailto:"]'));
                return links.map(a => a.href.replace('mailto:', '').trim());
            }
        """)
        for mail in mailtos:
            if "@" in mail:
                emails[mail.lower()] = "mailto-link"
    except:
        pass

    # Final filtering and context
    final = {}
    for email, src in emails.items():
        dom = email.split("@")[1] if "@" in email else ""
        if not any(bad in dom for bad in ["example.com", "test.com", "localhost"]):
            ctx = "donation-ready" if any(k in full.lower() for k in DONATION_KEYWORDS) else src
            final[email] = f"{ctx} @ {dom}"

    return final

async def main():
    all_emails = {}
    start_time = time.time()
    end_time = start_time + (RUN_DURATION_MINUTES * 60)

    print(f"🚀 Starting Automatic Reader-Focused Email Extractor v6.3.2")
    print(f"   Duration: {RUN_DURATION_MINUTES} minutes\n")

    async with async_playwright() as p:
        session_count = 0
        while time.time() < end_time:
            session_count += 1
            browser = None
            try:
                browser = await p.chromium.launch(
                    headless=True,                    # IMPORTANT: Changed to True for GitHub Actions
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-images",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage"
                    ]
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 820},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    locale="en-US"
                )
                page = await context.new_page()
                await page.add_init_script(STEALTH_INIT_SCRIPT)

                print(f"Session {session_count}: Visiting reader sites...")

                for url in READER_HUBS:
                    if time.time() > end_time:
                        break
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(2)
                        page_emails = await extract_emails(page, url)
                        if page_emails:
                            all_emails.update(page_emails)
                            print(f"   ✅ Found {len(page_emails)} emails from {url}")
                    except Exception as e:
                        print(f"   ⚠️ Skipped {url}: {str(e)[:100]}")

            except Exception as e:
                print(f"Session {session_count} error: {e}")
                traceback.print_exc()
            finally:
                if browser:
                    try:
                        await asyncio.wait_for(browser.close(), timeout=15)
                        print(f"   Browser closed gracefully")
                    except asyncio.TimeoutError:
                        print(f"   Browser close timeout")
                    except Exception as e:
                        print(f"   Error during browser close: {e}")

            if time.time() < end_time:
                await asyncio.sleep(random.uniform(8, 15))

    # Save results
    with open("collected_emails_v6.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "source", "domain", "context"])
        for email, src in all_emails.items():
            domain = email.split("@")[1] if "@" in email else ""
            context = src.split(" @ ")[0] if " @ " in src else src
            writer.writerow([email, src, domain, context])

    print(f"\n🏁 {RUN_DURATION_MINUTES}-minute run completed!")
    print(f"   Total unique emails: {len(all_emails)}")
    print("   → Check file: collected_emails_v6.csv")

if __name__ == "__main__":
    READER_HUBS = [
        "https://www.goodreads.com",
        "https://app.thestorygraph.com",
        "https://bookriot.com",
        "https://www.bookbrowse.com",
        "https://archiveofourown.org",
        "https://www.wattpad.com",
        "https://www.librarything.com",
    ]
    asyncio.run(main())
