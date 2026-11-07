import os
import time
from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright

app = FastAPI(title="RetroStress Token Harvester API")

BASE_URL = "https://retrostress.net"

CHROME_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-background-networking"
]

@app.get("/")
def health():
    return {"status": "online", "service": "RetroStress Harvester API"}

@app.get("/token")
def generate_one_token():
    t0 = time.time()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=CHROME_ARGS
            )
            try:
                ua = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
                context = browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())
                
                page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded", timeout=25000)
                btn = page.locator("#register-submit")

                for _ in range(20):
                    page.wait_for_timeout(500)
                    if not btn.is_disabled():
                        btn.click()
                        page.wait_for_timeout(800)
                        key = page.locator("#generated-key").input_value(timeout=3000)
                        if key and key.startswith("usr_"):
                            return {
                                "success": True,
                                "token": key,
                                "elapsed_seconds": round(time.time() - t0, 2)
                            }
                        break

                return {"success": False, "error": "Turnstile solve timeout"}
            finally:
                browser.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/batch")
def generate_batch(count: int = Query(default=5, ge=1, le=25)):
    results = []
    for _ in range(count):
        res = generate_one_token()
        if res.get("success"):
            results.append(res.get("token"))
    return {
        "success": True,
        "count": len(results),
        "tokens": results
    }

if __name__ == "__main__":
    import uvicorn
    # Railway passes PORT env variable (e.g. 6799), fallback to 6799 if not set
    port = int(os.environ.get("PORT", 6799))
    uvicorn.run(app, host="0.0.0.0", port=port)
