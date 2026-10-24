"""Render deck.html to the presentation PDF with headless Chromium."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
NAME = "AQI-Forecasting_YashGarg-I023_YashKothari-I037_AnumayPandey-I054.pdf"
AUTHORS = "Yash Garg (I023), Yash Kothari (I037), Anumay Pandey (I054)"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page()
    pg.goto((HERE / "deck.html").as_uri()); pg.wait_for_load_state("networkidle")
    pg.pdf(path=str(HERE / NAME), width="1280px", height="720px", print_background=True)
    b.close()

from pypdf import PdfReader, PdfWriter
w = PdfWriter(clone_from=PdfReader(HERE / NAME))
w.add_metadata({"/Title": "AQI Forecasting Lab", "/Author": AUTHORS,
                "/Subject": "Applied Time Series Analysis course project"})
w.write(HERE / NAME)
