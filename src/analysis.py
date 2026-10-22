"""Requirements 2, 4, 5, 6, 7: EDA, stationarity, transformations, decomposition, ACF/PACF."""
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.seasonal import MSTL, seasonal_decompose
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf

ALPHA = 0.05


# ---------- EDA ----------
def describe(s: pd.Series) -> dict:
    s = s.dropna()
    d = s.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95])
    out = {k: round(float(v), 2) for k, v in d.items()}
    out["skewness"] = round(float(stats.skew(s)), 3)
    out["excess_kurtosis"] = round(float(stats.kurtosis(s)), 3)
    out["log_skewness"] = round(float(stats.skew(np.log(s))), 3)
    return out


def qq_points(s: pd.Series, n: int = 400) -> dict:
    x = np.sort(s.dropna().values)
    pos = np.linspace(0, len(x) - 1, n).astype(int)
    probs = (pos + 0.5) / len(x)
    theo = stats.norm.ppf(probs)
    z = (x - x.mean()) / x.std()
    return {"theoretical": theo.round(4).tolist(), "sample": z[pos].round(4).tolist()}


def outliers(s: pd.Series, window: int = 30, z: float = 3.5) -> pd.DataFrame:
    """Robust rolling z-score on log AQI: flags unusual days relative to the local level."""
    ls = np.log(s)
    med = ls.rolling(window, center=True, min_periods=10).median()
    mad = (ls - med).abs().rolling(window, center=True, min_periods=10).median() * 1.4826
    rz = (ls - med) / mad
    flag = rz.abs() > z
    return pd.DataFrame({"aqi": s[flag], "robust_z": rz[flag].round(2)})


def seasonal_profiles(s: pd.Series) -> dict:
    s = s.dropna()
    wd = s.groupby(s.index.dayofweek).agg(["mean", "median", "std"]).round(1)
    mo = s.groupby(s.index.month).agg(["mean", "median", "std"]).round(1)
    yr = s.groupby(s.index.year).agg(["mean", "median", "std", "count"]).round(1)
    # Kruskal-Wallis: do weekdays / months differ in distribution?
    kw_wd = stats.kruskal(*[g.values for _, g in s.groupby(s.index.dayofweek)])
    kw_mo = stats.kruskal(*[g.values for _, g in s.groupby(s.index.month)])
    return {
        "weekday": wd.reset_index(names="weekday").to_dict("records"),
        "month": mo.reset_index(names="month").to_dict("records"),
        "year": yr.reset_index(names="year").to_dict("records"),
        "kruskal_weekday_p": float(kw_wd.pvalue),
        "kruskal_month_p": float(kw_mo.pvalue),
    }


# ---------- Stationarity ----------
def adf_test(x: pd.Series) -> dict:
    r = adfuller(x.dropna(), autolag="AIC")
    return {
        "test": "ADF",
        "h0": "Series has a unit root (non-stationary)",
        "statistic": round(float(r[0]), 4),
        "p_value": float(r[1]),
        "lags_used": int(r[2]),
        "critical_values": {k: round(float(v), 3) for k, v in r[4].items()},
        "conclusion": "Reject H0 -> stationary" if r[1] < ALPHA else "Fail to reject H0 -> unit root likely",
    }


def kpss_test(x: pd.Series, regression: str = "c") -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = kpss(x.dropna(), regression=regression, nlags="auto")
    return {
        "test": "KPSS",
        "h0": "Series is level-stationary" if regression == "c" else "Series is trend-stationary",
        "statistic": round(float(r[0]), 4),
        "p_value": float(r[1]),
        "lags_used": int(r[2]),
        "critical_values": {k: round(float(v), 3) for k, v in r[3].items()},
        "conclusion": "Reject H0 -> non-stationary" if r[1] < ALPHA else "Fail to reject H0 -> stationary",
        "note": "statsmodels caps KPSS p-values to [0.01, 0.10]",
    }


def stationarity_suite(variants: dict) -> list:
    rows = []
    for name, x in variants.items():
        a, k = adf_test(x), kpss_test(x)
        verdict = (
            "stationary" if a["p_value"] < ALPHA and k["p_value"] >= ALPHA
            else "non-stationary" if a["p_value"] >= ALPHA and k["p_value"] < ALPHA
            else "conflicting (ADF says stationary, KPSS says not)" if a["p_value"] < ALPHA
            else "conflicting (both fail to reject)"
        )
        rows.append({"series": name, "adf": a, "kpss": k, "verdict": verdict})
    return rows


def rolling_stats(s: pd.Series, window: int = 30) -> pd.DataFrame:
    return pd.DataFrame({"mean": s.rolling(window).mean(), "std": s.rolling(window).std()})


def boxcox_lambda(s: pd.Series) -> float:
    _, lam = stats.boxcox(s.dropna().values)
    return float(lam)


def variance_by_level(s: pd.Series) -> dict:
    """Does spread grow with level? Monthly mean vs monthly std on raw and log scales."""
    m = s.resample("MS")
    raw = pd.DataFrame({"mean": m.mean(), "std": m.std()}).dropna()
    lm = np.log(s).resample("MS")
    lg = pd.DataFrame({"mean": lm.mean(), "std": lm.std()}).dropna()
    return {
        "corr_mean_std_raw": round(float(raw["mean"].corr(raw["std"])), 3),
        "corr_mean_std_log": round(float(lg["mean"].corr(lg["std"])), 3),
    }


# ---------- Decomposition ----------
def mstl_decompose(y: pd.Series) -> pd.DataFrame:
    """Multiple-seasonal STL: weekly (7) and annual (365) seasonality + trend + residual."""
    res = MSTL(y, periods=(7, 365), stl_kwargs={"robust": True}).fit()
    out = pd.DataFrame({"observed": res.observed, "trend": res.trend, "resid": res.resid})
    seas = res.seasonal
    out["seasonal_weekly"] = seas["seasonal_7"]
    out["seasonal_annual"] = seas["seasonal_365"]
    # Smooth annual shape: least-squares fit of 3 annual harmonic pairs to the STL annual component.
    # With only ~5 values per calendar day, the raw STL component also carries year-specific episodes.
    t = (y.index - pd.Timestamp("2000-01-01")).days.values.astype(float)
    X = np.column_stack([np.ones_like(t)] + [f(2 * np.pi * k * t / 365.25) for k in (1, 2, 3) for f in (np.sin, np.cos)])
    beta, *_ = np.linalg.lstsq(X, out["seasonal_annual"].values, rcond=None)
    out["annual_fourier"] = X @ beta
    return out


def seasonal_strength(dec: pd.DataFrame) -> dict:
    """Hyndman's strength measures: 1 - Var(R)/Var(S+R), clipped at 0."""
    r = dec["resid"]
    f = lambda comp: round(max(0.0, 1 - r.var() / (dec[comp] + r).var()), 3)
    return {
        "trend_strength": round(max(0.0, 1 - r.var() / (dec["trend"] + r).var()), 3),
        "weekly_strength": round(f("seasonal_weekly"), 3),
        "annual_strength": round(f("seasonal_annual"), 3),
    }


def classical_monthly(s: pd.Series) -> pd.DataFrame:
    m = s.resample("MS").mean()
    r = seasonal_decompose(m, model="multiplicative", period=12)
    return pd.DataFrame({"observed": r.observed, "trend": r.trend, "seasonal": r.seasonal, "resid": r.resid})


# ---------- ACF / PACF ----------
def acf_pacf(x: pd.Series, nlags: int = 40) -> dict:
    x = x.dropna()
    a, aci = acf(x, nlags=nlags, alpha=ALPHA, fft=True)
    p, pci = pacf(x, nlags=nlags, alpha=ALPHA, method="ywm")
    band = 1.96 / np.sqrt(len(x))
    return {
        "lags": list(range(nlags + 1)),
        "acf": a.round(4).tolist(),
        "pacf": p.round(4).tolist(),
        "band": round(float(band), 4),
        "n": int(len(x)),
        "significant_pacf_lags": [i for i in range(1, nlags + 1) if abs(p[i]) > band],
        "significant_acf_lags": [i for i in range(1, nlags + 1) if abs(a[i]) > band],
    }
