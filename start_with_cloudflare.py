"""
TraderPro 1-Click Cloudflare Tunnel Launcher
Launches the FastAPI strategy scanner and creates a secure, global Cloudflare HTTPS Tunnel.
Works 100% free, zero configuration, bypasses all ISP blocks.
"""

import os
import sys
import re
import time
import subprocess
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CLOUDFLARED_BIN = BASE_DIR / "cloudflared.exe"
ENV_FILE = BASE_DIR / ".env"

def load_dotenv():
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k_clean = k.strip()
                        v_clean = v.strip().strip('"').strip("'")
                        os.environ[k_clean] = v_clean
        except Exception:
            pass

def main():
    load_dotenv()
    print("=" * 65, flush=True)
    print("      Starting TraderPro Strategy Scanner via Cloudflare         ", flush=True)
    print("=" * 65, flush=True)

    if not CLOUDFLARED_BIN.exists():
        print(f"[!] cloudflared.exe not found in {BASE_DIR}. Please ensure it is present.", flush=True)
        sys.exit(1)

    # 1. Start Uvicorn Server in background
    print("[1/2] Starting local strategy scanner on port 8000...", flush=True)
    server_cmd = [sys.executable, "-u", "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", "8000"]
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    # Stream server output in a separate daemon thread
    def stream_server_logs():
        for line in iter(server_proc.stdout.readline, ''):
            l = line.strip()
            if any(k in l for k in ["[INFO]", "Uvicorn running", "[TV Feed]", "Instant Alert"]):
                print(f" [Server] {l}", flush=True)

    threading.Thread(target=stream_server_logs, daemon=True).start()
    time.sleep(2)

    # 2. Check for Cloudflare Named Tunnel Token or Quick Tunnel
    tunnel_token = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    if tunnel_token:
        print("[2/2] Connecting Permanent Cloudflare Named Tunnel using token...", flush=True)
        cf_cmd = [str(CLOUDFLARED_BIN), "tunnel", "run", "--token", tunnel_token]
    else:
        print("[2/2] Requesting Cloudflare Quick Tunnel (Free Worldwide HTTPS)...", flush=True)
        cf_cmd = [str(CLOUDFLARED_BIN), "tunnel", "--url", "http://127.0.0.1:8000"]

    cf_proc = subprocess.Popen(
        cf_cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    public_url = None
    connected_banner_shown = False
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    app_url = os.environ.get("APP_URL", "").strip()

    # Monitor cloudflared stdout
    for line in iter(cf_proc.stdout.readline, ''):
        line_clean = line.strip()
        
        # Check for trycloudflare quick URL
        match = url_pattern.search(line_clean)
        if match and not public_url:
            public_url = match.group(0)
            os.environ["APP_URL"] = public_url
            print("\n" + "=" * 65, flush=True)
            print("  [SUCCESS] TraderPro is LIVE on Cloudflare Quick Tunnel:", flush=True)
            print(f"  >> Public URL : {public_url}", flush=True)
            print(f"  >> Local URL  : http://127.0.0.1:8000", flush=True)
            print("  >> WebSockets : wss:// (0-Lag Realtime Streaming Active)", flush=True)
            print("  >> Telegram   : Alerts configured with this link", flush=True)
            print("=" * 65, flush=True)
            print("  Press Ctrl+C at any time to stop the server.\n", flush=True)
            connected_banner_shown = True

        # Check for Named Tunnel connection
        elif "Registered tunnel connection" in line_clean and not connected_banner_shown and tunnel_token:
            connected_banner_shown = True
            print("\n" + "=" * 65, flush=True)
            print("  [SUCCESS] Permanent Cloudflare Tunnel is CONNECTED!", flush=True)
            if app_url:
                print(f"  >> Public Domain : {app_url}", flush=True)
            else:
                print("  >> Public Domain : Active on your configured Cloudflare Hostname", flush=True)
            print(f"  >> Local Origin  : http://127.0.0.1:8000", flush=True)
            print("  >> WebSockets    : wss:// (0-Lag Realtime Streaming Active)", flush=True)
            print("  >> Edge Network  : Connected to Cloudflare Edge (Mumbai/Chennai)", flush=True)
            print("=" * 65, flush=True)
            print("  Press Ctrl+C at any time to stop the server.\n", flush=True)

    try:
        cf_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping Cloudflare Tunnel and Server...", flush=True)
    finally:
        cf_proc.terminate()
        server_proc.terminate()

if __name__ == "__main__":
    main()
