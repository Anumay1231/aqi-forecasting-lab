"""Localhost dashboard backend (Requirement 11).

Run:  python -m uvicorn app.server:app --port 8000
Forecasts are produced live from the trained pipeline (production parameters estimated by
run_pipeline.py on all data up to the last observation), never hardcoded.
"""
import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.config import ARTIFACTS, AQI_BANDS, CITIES, PROCESSED_DIR, city_slug
from src.evaluation import future_forecast
from src.models import spec_from_dict

STATIC = Path(__file__).parent / "static"
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

app = FastAPI(title="AQI Time Series Forecasting")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@lru_cache(maxsize=8)
def artifact(city: str) -> dict:
    p = ARTIFACTS / f"{city_slug(city)}.json"
    if not p.exists():
        raise HTTPException(404, f"No trained artifacts for {city}. Run: python run_pipeline.py {city}")
    return json.loads(p.read_text())


@lru_cache(maxsize=8)
def series(city: str) -> pd.Series:
    df = pd.read_csv(PROCESSED_DIR / f"{city_slug(city)}_daily.csv", parse_dates=["date"], index_col="date")
    s = df["log_aqi"].asfreq("D")
    return s


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/vendor/plotly.min.js")
def plotly_js():
    return FileResponse(PLOTLY_JS, media_type="application/javascript")


@app.get("/api/cities")
def cities():
    avail = [c for c in CITIES if (ARTIFACTS / f"{city_slug(c)}.json").exists()]
    return {"cities": avail, "bands": AQI_BANDS}


@app.get("/api/city/{city}")
def city(city: str):
    return JSONResponse(artifact(city))


def _forecast(city: str, model: str | None, h: int) -> tuple[str, pd.DataFrame]:
    a = artifact(city)
    model = model or a["selected_model"]
    prod = a["production"].get(model)
    if prod is None:
        raise HTTPException(404, f"Unknown model {model}")
    spec = spec_from_dict(prod["spec"])
    df = future_forecast(spec, series(city), prod["params"], h)
    return model, df


@app.get("/api/forecast")
def forecast(city: str, model: str | None = None, h: int = Query(7, ge=1, le=30), history: int = 120):
    model, df = _forecast(city, model, h)
    s = np.exp(series(city)).iloc[-history:]
    return {
        "city": city, "model": model, "h": h,
        "history": {"date": s.index.strftime("%Y-%m-%d").tolist(), "aqi": s.round(1).tolist()},
        "forecast": {
            "date": df["date"].dt.strftime("%Y-%m-%d").tolist(),
            **{c: df[c].round(1).tolist() for c in ["forecast", "lo80", "hi80", "lo95", "hi95"]},
            "category": df["category"].tolist(),
        },
    }


@app.get("/api/forecast.csv")
def forecast_csv(city: str, model: str | None = None, h: int = Query(7, ge=1, le=30)):
    model, df = _forecast(city, model, h)
    df = df.copy()
    df.insert(0, "city", city)
    df.insert(1, "model", model)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    buf.write("# Statistical estimate only; not an official CPCB AQI forecast or health advice.\n")
    df.round(1).to_csv(buf, index=False)
    buf.seek(0)
    fname = f"aqi_forecast_{city_slug(city)}_{h}d.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
