"""Rolling-origin forecasting, accuracy metrics, interval coverage, residual diagnostics."""
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf

from .config import AQI_BANDS, aqi_category
from .models import Spec, fit, refilter

Z80, Z95 = stats.norm.ppf(0.9), stats.norm.ppf(0.975)


def _paths_statespace(spec: Spec, res, positions, max_h, last_pos):
    out = []
    for pos in positions:
        end = min(pos + max_h, last_pos)
        if end <= pos:
            continue
        if spec.kind == "ets":
            pr = res.get_prediction(start=pos + 1, end=end, dynamic=0, method="exact")
            mean = np.asarray(pr.predicted_mean)
            se = np.sqrt(np.asarray(pr.var_pred_mean if hasattr(pr, "var_pred_mean") else pr.var))
        else:
            pr = res.get_prediction(start=pos + 1, end=end, dynamic=True)
            mean = np.asarray(pr.predicted_mean)
            se = np.asarray(pr.se_mean)
        for i in range(len(mean)):
            out.append((pos, pos + 1 + i, i + 1, mean[i], se[i]))
    return out


def _paths_naive(spec: Spec, y: np.ndarray, train_y: pd.Series, positions, max_h, last_pos):
    ly = np.log(train_y.dropna())
    if spec.kind == "naive":
        sigma = float(ly.diff().std())
    else:
        sigma = float(ly.diff(7).std())
    out = []
    for pos in positions:
        for h in range(1, max_h + 1):
            t = pos + h
            if t > last_pos:
                break
            if spec.kind == "naive":
                m, se = y[pos], sigma * np.sqrt(h)
            else:
                m, se = y[t - 7], sigma  # same weekday last week; h<=7 so always observed
            out.append((pos, t, h, m, se))
    return out


def rolling_forecasts(spec: Spec, ylog: pd.Series, fit_end: str, eval_start: str, eval_end: str,
                      max_h: int = 7, fitted=None):
    """Fit on data <= fit_end once, then forecast 1..max_h steps from every origin in
    [eval_start - 1 day, eval_end - 1 day]. States are updated with each new observation,
    parameters stay fixed (no information from after the origin is used)."""
    y = ylog[:eval_end]
    idx = y.index
    first = idx.get_loc(pd.Timestamp(eval_start))
    last = len(idx) - 1
    positions = range(first - 1, last)
    if spec.kind in ("naive", "snaive"):
        rows = _paths_naive(spec, y.values, np.exp(ylog[:fit_end]), positions, max_h, last)
        res = None
    else:
        res = fitted if fitted is not None else fit(spec, ylog[:fit_end])
        full = refilter(spec, y, res.params)
        rows = _paths_statespace(spec, full, positions, max_h, last)
    df = pd.DataFrame(rows, columns=["origin_pos", "target_pos", "h", "mean_log", "se_log"])
    df["origin"] = idx[df["origin_pos"]]
    df["date"] = idx[df["target_pos"]]
    df["actual"] = np.exp(y.values[df["target_pos"]])
    df = df[df["date"] >= pd.Timestamp(eval_start)]
    return to_aqi_scale(df.drop(columns=["origin_pos", "target_pos"])), res


def to_aqi_scale(df: pd.DataFrame) -> pd.DataFrame:
    m, s = df["mean_log"], df["se_log"]
    clip = lambda v: np.clip(np.exp(v), 0, 500)
    df = df.copy()
    df["forecast"] = clip(m)
    df["lo80"], df["hi80"] = clip(m - Z80 * s), clip(m + Z80 * s)
    df["lo95"], df["hi95"] = clip(m - Z95 * s), clip(m + Z95 * s)
    return df


def metrics(df: pd.DataFrame, mase_scale: float) -> dict:
    a, f = df["actual"].values, df["forecast"].values
    e = a - f
    cat_a = np.array([aqi_category(v) for v in a])
    cat_f = np.array([aqi_category(v) for v in f])
    return {
        "n": int(len(df)),
        "MAE": round(float(np.mean(np.abs(e))), 2),
        "RMSE": round(float(np.sqrt(np.mean(e ** 2))), 2),
        "MAPE": round(float(100 * np.mean(np.abs(e) / a)), 2),
        "sMAPE": round(float(100 * np.mean(2 * np.abs(e) / (np.abs(a) + np.abs(f)))), 2),
        "MASE": round(float(np.mean(np.abs(e)) / mase_scale), 3),
        "bias": round(float(np.mean(f - a)), 2),
        "cov80": round(float(np.mean((a >= df["lo80"]) & (a <= df["hi80"])) * 100), 1),
        "cov95": round(float(np.mean((a >= df["lo95"]) & (a <= df["hi95"])) * 100), 1),
        "category_acc": round(float(np.mean(cat_a == cat_f) * 100), 1),
    }


def metric_table(fc: dict, horizons, mase_scale) -> list:
    rows = []
    for name, df in fc.items():
        for h in horizons:
            r = metrics(df[df["h"] == h], mase_scale)
            rows.append({"model": name, "h": h, **r})
    return rows


def diebold_mariano(e_model: np.ndarray, e_bench: np.ndarray, h: int) -> dict:
    """DM test (squared-error loss) with the Harvey-Leybourne-Newbold small-sample correction.
    H0: equal accuracy. Negative statistic = model more accurate than the benchmark."""
    d = e_model ** 2 - e_bench ** 2
    n = len(d)
    dbar = d.mean()
    gam = [np.sum((d[k:] - dbar) * (d[:n - k] - dbar)) / n for k in range(h)]
    var = (gam[0] + 2 * sum(gam[1:])) / n
    if var <= 0:
        return {"stat": None, "p_value": None}
    dm = dbar / np.sqrt(var)
    dm *= np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    p = 2 * stats.t.sf(abs(dm), df=n - 1)
    return {"stat": round(float(dm), 3), "p_value": float(p)}


def dm_table(fc: dict, horizons, bench: str = "Naive") -> list:
    rows = []
    for name, df in fc.items():
        if name == bench:
            continue
        for h in horizons:
            a = df[df["h"] == h].set_index("date")
            b = fc[bench][fc[bench]["h"] == h].set_index("date")
            j = a.index.intersection(b.index)
            r = diebold_mariano((a.loc[j, "actual"] - a.loc[j, "forecast"]).values,
                                (b.loc[j, "actual"] - b.loc[j, "forecast"]).values, h)
            rows.append({"model": name, "h": h, **r})
    return rows


def mase_scale(train_aqi: pd.Series) -> float:
    """In-sample MAE of the 1-step naive forecast on the training data (original scale)."""
    return float(train_aqi.diff().abs().mean())


def residual_diagnostics(spec: Spec, res, burn: int = 30) -> dict:
    r = res.resid if isinstance(res.resid, pd.Series) else pd.Series(np.asarray(res.resid), index=res.model.data.row_labels)
    r = r.iloc[burn:].dropna()
    k = sum(spec.order[::2]) + spec.seasonal_order[0] + spec.seasonal_order[2]
    lb = acorr_ljungbox(r, lags=[7, 14, 28], model_df=min(k, 6), return_df=True)
    jb = stats.jarque_bera(r)
    a = acf(r, nlags=40, fft=True)
    x = np.sort(((r - r.mean()) / r.std()).values)
    pos = np.linspace(0, len(x) - 1, 300).astype(int)
    half = len(r) // 2
    return {
        "mean": round(float(r.mean()), 4),
        "std": round(float(r.std()), 4),
        "var_first_half": round(float(r.iloc[:half].var()), 4),
        "var_second_half": round(float(r.iloc[half:].var()), 4),
        "ljung_box": [{"lag": int(l), "stat": round(float(s), 2), "p_value": float(p)}
                      for l, s, p in zip(lb.index, lb["lb_stat"], lb["lb_pvalue"])],
        "jarque_bera": {"stat": round(float(jb.statistic), 2), "p_value": float(jb.pvalue),
                        "skew": round(float(stats.skew(r)), 3),
                        "excess_kurtosis": round(float(stats.kurtosis(r)), 3)},
        "acf": a.round(4).tolist(),
        "band": round(1.96 / np.sqrt(len(r)), 4),
        "series": {"date": [d.strftime("%Y-%m-%d") for d in r.index], "value": r.round(4).tolist()},
        "qq": {"theoretical": stats.norm.ppf((pos + 0.5) / len(x)).round(4).tolist(),
               "sample": x[pos].round(4).tolist()},
    }


def future_forecast(spec: Spec, ylog: pd.Series, params, h: int) -> pd.DataFrame:
    """Forecast h days beyond the last observation using fixed, pre-estimated parameters."""
    last = ylog.index[-1]
    dates = pd.date_range(last + pd.Timedelta(days=1), periods=h, freq="D")
    if spec.kind in ("naive", "snaive"):
        ly = ylog.dropna()
        if spec.kind == "naive":
            m = np.repeat(ly.iloc[-1], h)
            se = params["sigma"] * np.sqrt(np.arange(1, h + 1))
        else:
            m = np.array([ly.iloc[-7 + (i % 7)] for i in range(h)])
            se = params["sigma"] * np.sqrt(np.arange(h) // 7 + 1)
    else:
        res = refilter(spec, ylog, np.asarray(params))
        if spec.kind == "ets":
            pr = res.get_prediction(start=len(ylog), end=len(ylog) + h - 1, method="exact")
            m = np.asarray(pr.predicted_mean)
            se = np.sqrt(np.asarray(pr.var_pred_mean if hasattr(pr, "var_pred_mean") else pr.var))
        else:
            from .models import fourier
            pr = res.get_forecast(steps=h, exog=fourier(dates, spec.fourier_k))
            m, se = np.asarray(pr.predicted_mean), np.asarray(pr.se_mean)
    df = pd.DataFrame({"date": dates, "h": np.arange(1, h + 1), "mean_log": m, "se_log": se})
    df = to_aqi_scale(df)
    df["category"] = [aqi_category(v) for v in df["forecast"]]
    return df.drop(columns=["mean_log", "se_log"])


__all__ = ["rolling_forecasts", "metric_table", "mase_scale", "residual_diagnostics",
           "future_forecast", "AQI_BANDS"]
