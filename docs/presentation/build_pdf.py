"""Render deck.html to AQI-Forecasting-Presentation.pdf with headless Chromium."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page()
    pg.goto((HERE / "deck.html").as_uri()); pg.wait_for_load_state("networkidle")
    pg.pdf(path=str(HERE / "AQI-Forecasting-Presentation.pdf"), width="1280px", height="720px", print_background=True)
    b.close()
