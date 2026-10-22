"""End-to-end pipeline: runs all 11 workflow steps for a city and writes artifacts/<city>.json.

Usage:  python run_pipeline.py            (all configured cities)
        python run_pipeline.py Mumbai
"""
import json
import sys
import time

import numpy as np
import pandas as pd

from src import analysis as an
from src import data as dl
from src import evaluation as ev
from src import models as md
from src.config import (ARTIFACTS, CITIES, HORIZONS, MAX_H, PROCESSED_DIR, SOURCE,
                        TEST_END, TRAIN_END, VAL_END, city_slug)


def ser(s: pd.Series, nd: int = 3) -> dict:
    s = s.dropna() if s.dtype.kind == "f" else s
    return {"date": [d.strftime("%Y-%m-%d") for d in s.index],
            "value": [None if pd.isna(v) else round(float(v), nd) for v in s.values]}


def jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def run_city(city: str):
    t0 = time.time()
    log = lambda *a: print(f"[{city} {time.time() - t0:6.1f}s]", *a, flush=True)
    start = CITIES[city]["model_start"]
    out = {"city": city, "model_start": start, "splits": {
        "train": [start, TRAIN_END], "validation": ["2024-01-01", VAL_END],
        "test": ["2025-01-01", TEST_END]}, "source": SOURCE, "horizons": HORIZONS}

    # ---- 1. Data collection
    raw = dl.load_raw()
    cf = dl.city_frame(raw, city)
    out["data_card"] = dl.data_card(raw, cf, city)
    out["history"] = {"date": [d.strftime("%Y-%m-%d") for d in cf.index],
                      "aqi": [None if pd.isna(v) else float(v) for v in cf["aqi"]],
                      "stations": [None if pd.isna(v) else float(v) for v in cf["no_stations"]]}
    st = cf["no_stations"].groupby(cf.index.year).median()
    out["stations_by_year"] = {int(k): float(v) for k, v in st.items()}
    log("data loaded")

    # ---- 3. Missing values
    out["missing"] = dl.missingness_summary(cf, start)
    window = cf["aqi"][start:TEST_END]
    out["imputation_comparison"] = dl.compare_imputation(window[:VAL_END])
    s = dl.impute(window, "time")
    out["missing"]["after_imputation"] = int(s.isna().sum())
    y = np.log(s)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"aqi": s, "log_aqi": y, "was_imputed": window.isna()}).to_csv(
        PROCESSED_DIR / f"{city_slug(city)}_daily.csv", index_label="date")
    log("missing handled")

    # ---- 2. EDA
    train = s[:TRAIN_END]
    out["eda"] = {
        "describe_window": an.describe(s),
        "describe_full": an.describe(cf["aqi"]),
        "values_window": s.round(0).tolist(),
        "qq_raw": an.qq_points(s),
        "qq_log": an.qq_points(y),
        "seasonal": an.seasonal_profiles(s),
        "pollutants": cf[start:]["prominent_pollutant"].value_counts().head(8).to_dict(),
        "lag_scatter": {"x": s.shift(1).dropna().round(0).tolist(), "y": s.iloc[1:].round(0).tolist(),
                        "corr_lag1": round(float(s.autocorr(1)), 3),
                        "corr_lag7": round(float(s.autocorr(7)), 3),
                        "corr_lag365": round(float(s.autocorr(365)), 3)},
        "duplicates": out["data_card"]["duplicates_city_date"],
    }
    o = an.outliers(s)
    out["eda"]["outliers"] = [{"date": d.strftime("%Y-%m-%d"), "aqi": float(r.aqi), "robust_z": float(r.robust_z)}
                              for d, r in o.iterrows()]
    log("eda done")

    # ---- 4/5. Stationarity + transformations (training data only)
    ytr = y[:TRAIN_END]
    variants = {"AQI": train, "log AQI": ytr, "Δ log AQI (d=1)": ytr.diff(),
                "Δ₇ log AQI (D=1, s=7)": ytr.diff(7), "Δ Δ₇ log AQI": ytr.diff(7).diff()}
    out["stationarity"] = an.stationarity_suite(variants)
    rs = an.rolling_stats(train, 30)
    rl = an.rolling_stats(ytr, 30)
    out["rolling"] = {"aqi_mean": ser(rs["mean"], 1), "aqi_std": ser(rs["std"], 1),
                      "log_mean": ser(rl["mean"]), "log_std": ser(rl["std"])}
    out["transform"] = {"boxcox_lambda": round(an.boxcox_lambda(train), 3), **an.variance_by_level(train)}
    log("stationarity done")

    # ---- 6. Decomposition
    dec = an.mstl_decompose(ytr)
    out["decomposition"] = {c: ser(dec[c], 4) for c in dec.columns}
    out["decomposition"]["strength"] = an.seasonal_strength(dec)
    cm = an.classical_monthly(train)
    out["classical_monthly"] = {c: ser(cm[c], 3) for c in cm.columns}
    log("decomposition done")

    # ---- 7. ACF / PACF
    out["acf_pacf"] = {"log AQI": an.acf_pacf(ytr, 40), "Δ log AQI": an.acf_pacf(ytr.diff(), 40),
                       "MSTL residual": an.acf_pacf(dec["resid"], 40),
                       "log AQI (long, 400 lags)": {k: v for k, v in an.acf_pacf(ytr, 400).items() if k != "pacf"}}
    log("acf/pacf done")

    # ---- 8/9/10. Order search + AIC/BIC on training data
    cands, best = md.search(ytr, log=lambda m: None)
    out["candidates"] = cands
    out["selected_orders"] = {f: sp.to_dict() for f, sp in best.items()}
    log("order search done:", {f: sp.label for f, sp in best.items()})

    specs = md.baseline_specs() + [best[f] for f in ["AR", "MA", "ARMA", "ARIMA", "SARIMA", "SARIMAX-Fourier"]]
    scale = ev.mase_scale(s[:TRAIN_END])

    # Validation: fit <= 2023, rolling forecasts across 2024
    val_fc = {}
    for sp in specs:
        val_fc[sp.label], _ = ev.rolling_forecasts(sp, y, TRAIN_END, "2024-01-01", VAL_END, MAX_H)
    out["validation_metrics"] = ev.metric_table(val_fc, HORIZONS, scale)
    vm = pd.DataFrame(out["validation_metrics"]).groupby("model")["RMSE"].mean().sort_values()
    out["selected_model"] = vm.index[0]
    log("validation done; best =", vm.index[0])

    # Test: refit <= 2024, rolling forecasts across 2025 (never seen during selection)
    test_fc, fits = {}, {}
    for sp in specs:
        test_fc[sp.label], fits[sp.label] = ev.rolling_forecasts(sp, y, VAL_END, "2025-01-01", TEST_END, MAX_H)
    out["test_metrics"] = ev.metric_table(test_fc, HORIZONS, scale)
    out["dm_tests"] = ev.dm_table(test_fc, HORIZONS)
    out["test_paths"] = {}
    for name, df in test_fc.items():
        out["test_paths"][name] = {}
        for h in HORIZONS:
            d = df[df["h"] == h]
            out["test_paths"][name][str(h)] = {
                "date": d["date"].dt.strftime("%Y-%m-%d").tolist(), "actual": d["actual"].round(1).tolist(),
                **{c: d[c].round(1).tolist() for c in ["forecast", "lo80", "hi80", "lo95", "hi95"]}}
    log("test done")

    # Residual diagnostics + in-sample info for each fitted statistical model
    out["diagnostics"] = {}
    for sp in specs:
        res = fits[sp.label]
        if res is None:
            continue
        out["diagnostics"][sp.label] = ev.residual_diagnostics(sp, res)
    log("diagnostics done")

    # Production parameters: refit on everything up to the last observation
    out["production"] = {}
    for sp in specs:
        if sp.kind == "naive":
            p = {"sigma": float(y.diff().std())}
        elif sp.kind == "snaive":
            p = {"sigma": float(y.diff(7).std())}
        else:
            p = md.fit(sp, y).params
            p = np.asarray(p).tolist()
        out["production"][sp.label] = {"spec": {**sp.to_dict(), "params": {}}, "params": p}
    out["last_observation"] = y.index[-1].strftime("%Y-%m-%d")
    log("production refit done")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{city_slug(city)}.json"
    path.write_text(json.dumps(out, default=jsonable))
    log(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    for c in (sys.argv[1:] or list(CITIES)):
        run_city(c)
