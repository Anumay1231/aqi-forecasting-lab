"""Start the dashboard and open it in the browser.

Trains the models first if the artifacts are missing (about 3 minutes per city).
Usage:  python serve.py            (port 8000, or set the PORT environment variable)
"""
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.config import ARTIFACTS, CITIES, city_slug  # noqa: E402


def free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit(f"No free port found between {preferred} and {preferred + 19}.")


def main():
    missing = [c for c in CITIES if not (ARTIFACTS / f"{city_slug(c)}.json").exists()]
    if missing:
        print(f"Training models for {', '.join(missing)} (first run only, about 3 minutes per city)...")
        import run_pipeline
        for c in missing:
            run_pipeline.run_city(c)

    import uvicorn

    port = free_port(int(os.environ.get("PORT", "8000")))
    url = f"http://localhost:{port}"
    print(f"\n  AQI Forecasting Lab is running at {url}\n  Press Ctrl+C to stop.\n")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run("app.server:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
