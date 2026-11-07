import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from playwright.sync_api import sync_playwright

BASE_URL = "https://retrostress.net"
TOKENS_FILE = "tokens.json"

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--window-size=1280,720",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-first-run",
    "--disable-extensions",
]

file_lock = Lock()
counter_lock = Lock()
git_lock = Lock()
stop_event = Event()
created_count = 0
last_git_push = 0

def load_existing_tokens():
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, list):
                        return list(dict.fromkeys(data))
        except Exception:
            pass
    return []

def append_and_sync_token(token, amount_needed):
    global last_git_push
    with file_lock:
        tokens = load_existing_tokens()
        if token and token not in tokens:
            tokens.append(token)
            with open(TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f, indent=2)

    now = time.time()
    if (created_count % 3 == 0 or created_count >= amount_needed) and (now - last_git_push > 10):
        with git_lock:
            try:
                subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], capture_output=True, timeout=10)
                subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], capture_output=True, timeout=10)
                subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, timeout=15)
                subprocess.run(["git", "add", TOKENS_FILE], capture_output=True, timeout=10)
                res = subprocess.run(["git", "commit", "-m", f"Auto-harvested tokens [skip ci]"], capture_output=True, timeout=10)
                if res.returncode == 0:
                    subprocess.run(["git", "push"], capture_output=True, timeout=20)
                    last_git_push = time.time()
                    print(f"[*] Git sync: pushed to main branch", flush=True)
            except Exception as e:
                print(f"[!] Git sync error: {e}", flush=True)

    return len(load_existing_tokens())

def worker_loop(worker_id, amount_needed):
    global created_count
    print(f"[*] Worker #{worker_id} initializing browser...", flush=True)
    try:
        with sync_playwright() as p:
            # Try official chrome channel first, fallback to chromium
            try:
                browser = p.chromium.launch(
                    channel="chrome",
                    headless=True,
                    args=LAUNCH_ARGS
                )
                btype = "Google Chrome"
            except Exception:
                browser = p.chromium.launch(
                    headless=True,
                    args=LAUNCH_ARGS
                )
                btype = "Chromium"

            print(f"[*] Worker #{worker_id} launched with {btype} v{browser.version}", flush=True)

            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
            )
            
            while not stop_event.is_set():
                with counter_lock:
                    if created_count >= amount_needed:
                        stop_event.set()
                        break

                page = None
                try:
                    page = context.new_page()
                    # Stealth injection
                    page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        window.chrome = { runtime: {} };
                    """)

                    t0 = time.time()
                    page.goto(f"{BASE_URL}/register", wait_until="networkidle", timeout=30000)
                    btn = page.locator("#register-submit")

                    print(f"[*] Worker #{worker_id}: Page loaded ({round(time.time() - t0, 1)}s), waiting for Turnstile...", flush=True)

                    solved = False
                    for sec in range(25):
                        if stop_event.is_set():
                            break
                        page.wait_for_timeout(1000)
                        if not btn.is_disabled():
                            solved = True
                            print(f"[+] Worker #{worker_id}: Turnstile solved in {sec + 1}s! Submitting...", flush=True)
                            btn.click()
                            page.wait_for_timeout(1000)
                            key = page.locator("#generated-key").input_value(timeout=4000)
                            if key and key.startswith("usr_"):
                                with counter_lock:
                                    if created_count < amount_needed:
                                        created_count += 1
                                        total = append_and_sync_token(key, amount_needed)
                                        print(f"[+] Added ({created_count}/{amount_needed}) -> {key} (Total pool: {total})", flush=True)
                                        if created_count >= amount_needed:
                                            stop_event.set()
                            else:
                                print(f"[!] Worker #{worker_id}: Submit clicked but invalid key returned", flush=True)
                            break

                    if not solved and not stop_event.is_set():
                        print(f"[-] Worker #{worker_id}: Turnstile timed out after 25s, recycling page...", flush=True)

                    page.close()
                except Exception as err:
                    print(f"[!] Worker #{worker_id} error: {err}", flush=True)
                    if page:
                        try:
                            page.close()
                        except Exception:
                            pass
                    time.sleep(1)

            try:
                browser.close()
            except Exception:
                pass
    except Exception as fatal:
        print(f"[!] Worker #{worker_id} fatal: {fatal}", flush=True)

def main():
    add_amount = 20
    concurrency = 4

    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        add_amount = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        concurrency = int(sys.argv[2])

    existing = load_existing_tokens()
    current_pool = len(existing)

    print("[*] GitHub Cloud Harvester Starting...", flush=True)
    print(f"[*] Amount to ADD  : +{add_amount}", flush=True)
    print(f"[*] Active Workers : {concurrency}", flush=True)
    print(f"[*] Current Pool   : {current_pool} token(s)", flush=True)
    print(f"[*] Expected Total : {current_pool + add_amount} token(s)\n", flush=True)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_loop, i + 1, add_amount) for i in range(concurrency)]
        for f in futures:
            f.result()

    append_and_sync_token("", 0)
    final_pool = len(load_existing_tokens())
    print(f"\n[+] Finished. Total tokens in pool: {final_pool} (Saved & pushed to repo)", flush=True)

if __name__ == "__main__":
    main()
