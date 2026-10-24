"""Capture dashboard screenshots from a running server (python serve.py)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "shots"; OUT.mkdir(exist_ok=True)
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg.goto(URL); pg.wait_for_selector("#content:not([hidden])", timeout=60000); pg.wait_for_timeout(2500)
    pg.screenshot(path=OUT / "dashboard.png")
    for sid in ["forecast", "models", "aic", "diagnostics"]:
        el = pg.locator(f"section#{sid}"); el.scroll_into_view_if_needed(); pg.wait_for_timeout(1200)
        el.screenshot(path=OUT / f"{sid}.png")
    pg.emulate_media(color_scheme="dark"); pg.reload(); pg.wait_for_selector("#content:not([hidden])"); pg.wait_for_timeout(2500)
    pg.screenshot(path=OUT / "dashboard_dark.png")
    b.close()
