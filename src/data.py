"""Requirement 1 & 3: loading, regular daily index, missing-value analysis and imputation."""
import numpy as np
import pandas as pd

from .config import RAW_CSV


def load_raw(path=RAW_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["aqi"] = pd.to_numeric(df["aqi"], errors="coerce")
    return df.sort_values(["city", "date"]).reset_index(drop=True)


def city_frame(df: pd.DataFrame, city: str) -> pd.DataFrame:
    """One city on a complete daily calendar. Missing days become NaN rows (never 0)."""
    c = df[df["city"] == city].drop_duplicates("date").set_index("date").sort_index()
    full = pd.date_range(c.index.min(), c.index.max(), freq="D", name="date")
    c = c.reindex(full)
    c["city"] = city
    c["is_missing"] = c["aqi"].isna()
    return c[["aqi", "no_stations", "aqi_category", "prominent_pollutant", "is_missing"]]


def data_card(df: pd.DataFrame, cf: pd.DataFrame, city: str) -> dict:
    return {
        "rows_all_cities": int(len(df)),
        "n_cities": int(df["city"].nunique()),
        "columns": list(df.columns),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "city": city,
        "city_first": str(cf.index.min().date()),
        "city_last": str(cf.index.max().date()),
        "city_calendar_days": int(len(cf)),
        "city_observed_days": int(cf["aqi"].notna().sum()),
        "duplicates_city_date": int(df.duplicated(["city", "date"]).sum()),
        "zero_aqi_values": int((cf["aqi"] == 0).sum()),
        "frequency": "daily (one bulletin per day, city AQI = average of station AQIs)",
        "units": "CPCB National AQI, dimensionless 0-500",
    }


def missing_runs(s: pd.Series) -> pd.DataFrame:
    """Contiguous runs of missing days: start, end, length."""
    na = s.isna()
    if not na.any():
        return pd.DataFrame(columns=["start", "end", "length"])
    grp = (na != na.shift()).cumsum()
    runs = s[na].groupby(grp[na]).apply(lambda x: (x.index.min(), x.index.max(), len(x)))
    return pd.DataFrame(runs.tolist(), columns=["start", "end", "length"])


def missingness_summary(cf: pd.DataFrame, model_start: str) -> dict:
    s = cf["aqi"]
    runs = missing_runs(s)
    win = s[model_start:]
    wruns = missing_runs(win)
    by_year = s.isna().groupby(s.index.year).sum().astype(int)
    return {
        "full_missing_days": int(s.isna().sum()),
        "full_missing_pct": round(100 * s.isna().mean(), 2),
        "full_longest_gap": int(runs["length"].max()) if len(runs) else 0,
        "full_gap_length_counts": {int(k): int(v) for k, v in runs["length"].value_counts().sort_index().items()},
        "window_missing_days": int(win.isna().sum()),
        "window_missing_pct": round(100 * win.isna().mean(), 3),
        "window_longest_gap": int(wruns["length"].max()) if len(wruns) else 0,
        "window_missing_dates": [d.strftime("%Y-%m-%d") for d in win[win.isna()].index],
        "missing_by_year": {int(k): int(v) for k, v in by_year.items()},
        "missing_by_weekday": {int(k): int(v) for k, v in s.isna().groupby(s.index.dayofweek).sum().items()},
    }


MAX_INTERP_GAP = 3  # never interpolate across longer gaps


def impute(s: pd.Series, method: str = "time", max_gap: int = MAX_INTERP_GAP) -> pd.Series:
    """Fill only gaps of <= max_gap days; longer gaps stay NaN (state-space models handle them)."""
    na = s.isna()
    grp = (na != na.shift()).cumsum()
    run_len = na.groupby(grp).transform("sum")
    fillable = na & (run_len <= max_gap)
    if method == "time":
        filled = np.exp(np.log(s).interpolate(method="time", limit_area="inside"))
    elif method == "ffill":
        filled = s.ffill()
    elif method == "weekly":  # same weekday previous week
        filled = s.fillna(s.shift(7))
    else:
        raise ValueError(method)
    out = s.copy()
    out[fillable] = filled[fillable]
    return out


def compare_imputation(s: pd.Series, n_trials: int = 300, seed: int = 0) -> list:
    """Hide known values in 1-3 day blocks and score each method (MAE in AQI units)."""
    rng = np.random.default_rng(seed)
    obs = s.dropna()
    idx = obs.index[10:-10]
    results = {m: [] for m in ["time", "ffill", "weekly"]}
    for _ in range(n_trials):
        L = int(rng.integers(1, 4))
        start = idx[int(rng.integers(0, len(idx) - L))]
        block = pd.date_range(start, periods=L, freq="D")
        if s.reindex(block).isna().any():
            continue
        masked = s.copy()
        masked[block] = np.nan
        for m in results:
            est = impute(masked, m)[block]
            results[m].append(float(np.mean(np.abs(est - s[block]))))
    return [{"method": m, "mae": round(float(np.mean(v)), 2), "n_blocks": len(v)} for m, v in results.items()]
