"""Draw the presentation figures from artifacts/<city>.json (no retraining)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fig"
OUT.mkdir(exist_ok=True)

INK, BODY, MUTE, GRID = "#171717", "#4d4d4d", "#8f8f8f", "#ececec"
ACCENT, ACCENT_SOFT, GREY = "#0070f3", "#cfe2fd", "#a3a3a3"
plt.rcParams.update({
    "font.family": "Inter", "font.size": 11, "axes.edgecolor": "#d4d4d4", "axes.labelcolor": BODY,
    "xtick.color": MUTE, "ytick.color": MUTE, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 12, "axes.titleweight": 600,
    "axes.titlecolor": INK, "axes.titlelocation": "left", "axes.titlepad": 10, "figure.dpi": 200,
    "legend.frameon": False, "legend.fontsize": 10, "axes.axisbelow": True,
})

M = json.load(open(ROOT / "artifacts/mumbai.json"))
D = json.load(open(ROOT / "artifacts/delhi.json"))


def ts(block):
    return pd.Series(block["value"] if "value" in block else block["aqi"], index=pd.to_datetime(block["date"]))


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def date_axis(ax, fmt="%Y"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


# 1. Line graph: full history
s = pd.Series(M["history"]["aqi"], index=pd.to_datetime(M["history"]["date"]), dtype=float)
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.axvspan(pd.Timestamp("2015-08-01"), pd.Timestamp("2018-12-31"), color="#f5f5f5", zorder=0)
ax.plot(s.index, s.values, color=GREY, lw=0.6, label="Daily AQI")
ax.plot(s.rolling(30, min_periods=20).mean(), color=ACCENT, lw=1.6, label="30-day mean")
ax.text(pd.Timestamp("2016-01-01"), 470, "single station, excluded", color=MUTE, fontsize=10)
ax.text(pd.Timestamp("2019-02-01"), 470, "modelling window (7–24 stations)", color=ACCENT, fontsize=10)
ax.set_ylabel("AQI"); ax.set_ylim(0, 510); ax.legend(loc="upper right", ncols=2, bbox_to_anchor=(1, 0.93))
date_axis(ax); save(fig, "line")

# 2. Scatter (lag 1), histogram, QQ
e = M["eda"]
fig, axs = plt.subplots(1, 3, figsize=(12, 3.7))
x, y = np.array(e["lag_scatter"]["x"]), np.array(e["lag_scatter"]["y"])
axs[0].scatter(x, y, s=4, alpha=0.35, color=ACCENT, lw=0)
axs[0].set_title(f"Lag-1 scatter  (r = {e['lag_scatter']['corr_lag1']})")
axs[0].set_xlabel("AQI on day t"); axs[0].set_ylabel("AQI on day t+1")
v = np.array(e["values_window"])
axs[1].hist(v, bins=45, color=ACCENT, alpha=0.85)
axs[1].set_title(f"Histogram  (skew = {e['describe_window']['skewness']})"); axs[1].set_xlabel("AQI")
for key, col, lab in [("qq_raw", GREY, "raw AQI"), ("qq_log", ACCENT, "log AQI")]:
    q = e[key]
    t, sm = np.array(q["theoretical"]), np.array(q["sample"])
    z = (sm - sm.mean()) / sm.std()
    axs[2].scatter(t, z, s=5, color=col, label=lab, lw=0)
axs[2].plot([-3.5, 3.5], [-3.5, 3.5], color=INK, lw=0.8)
axs[2].set_title("Normal QQ plot (standardised)"); axs[2].set_xlabel("theoretical quantile"); axs[2].legend()
save(fig, "eda")

# 3. Missing values by year
mb = M["missing"]["missing_by_year"]
fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [1.3, 1]})
yrs = list(mb)
axs[0].bar(yrs, [mb[k] for k in yrs], color=[GREY if int(k) < 2019 else ACCENT for k in yrs])
for i, k in enumerate(yrs):
    axs[0].text(i, mb[k] + 2, mb[k], ha="center", fontsize=9, color=BODY)
axs[0].set_title("Missing days per year"); axs[0].grid(axis="x", visible=False)
imp = M["imputation_comparison"]
names = {"time": "Time interpolation", "ffill": "Forward fill", "weekly": "Same weekday last week"}
axs[1].barh([names[i["method"]] for i in imp][::-1], [i["mae"] for i in imp][::-1],
            color=[GREY, GREY, ACCENT])
for i, r in enumerate(imp[::-1]):
    axs[1].text(r["mae"] + 0.4, i, f"{r['mae']}", va="center", fontsize=10)
axs[1].set_title("Imputation test: MAE on 299 masked gaps"); axs[1].grid(axis="y", visible=False)
axs[1].set_xlim(0, 34)
save(fig, "missing")

# 4. Rolling mean / std: raw vs log
r = M["rolling"]
fig, axs = plt.subplots(1, 2, figsize=(12, 3.4))
for ax, (m, sd, title) in zip(axs, [("aqi_mean", "aqi_std", "Raw AQI"), ("log_mean", "log_std", "log AQI")]):
    a, b = ts(r[m]), ts(r[sd])
    ax.plot(a, color=ACCENT, lw=1.4, label="rolling mean")
    ax2 = ax.twinx(); ax2.plot(b, color=GREY, lw=1.2, label="rolling std"); ax2.grid(False)
    ax2.spines["right"].set_visible(True); ax2.tick_params(colors=MUTE)
    ax.set_title(f"{title}: 60-day rolling mean (blue) and std (grey)"); date_axis(ax)
save(fig, "rolling")

# 5. Decomposition (MSTL)
dc = M["decomposition"]
fig, axs = plt.subplots(4, 1, figsize=(11, 5.6), sharex=True)
for ax, key, title, col in zip(axs, ["observed", "trend", "seasonal_annual", "seasonal_weekly"],
                               ["log AQI (observed)", "Trend", "Annual seasonal", "Weekly seasonal"],
                               [GREY, INK, ACCENT, ACCENT]):
    q = ts(dc[key])
    ax.plot(q, color=col, lw=0.9 if key != "trend" else 1.6)
    ax.set_title(title, fontsize=10.5, pad=4)
date_axis(axs[-1]); save(fig, "decomp")

# 6. Monthly profile
mo = M["eda"]["seasonal"]["month"]
fig, ax = plt.subplots(figsize=(7, 3.2))
lab = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
vals = [m["mean"] for m in mo]
ax.bar(range(12), vals, color=[ACCENT if v >= 100 else ACCENT_SOFT for v in vals]); ax.set_xticks(range(12), lab)
ax.axhline(100, color=MUTE, lw=0.8, ls="--"); ax.text(11.4, 103, "100", color=MUTE, fontsize=9, ha="right")
ax.set_title("Mean AQI by month, 2019–2025"); ax.grid(axis="x", visible=False)
save(fig, "monthly")

# 7. ACF / PACF
fig, axs = plt.subplots(2, 2, figsize=(12, 4.6))
for row, key in enumerate(["log AQI", "Δ log AQI"]):
    a = M["acf_pacf"][key]
    for col, kind in enumerate(["acf", "pacf"]):
        ax = axs[row, col]
        lags, vals = np.array(a["lags"][1:]), np.array(a[kind][1:])
        ax.vlines(lags, 0, vals, color=ACCENT, lw=1.6)
        ax.scatter(lags, vals, s=10, color=ACCENT, zorder=3)
        ax.axhspan(-a["band"], a["band"], color=ACCENT_SOFT, alpha=0.6, lw=0)
        ax.axhline(0, color=INK, lw=0.6)
        ax.set_title(f"{kind.upper()} of {key}", fontsize=11)
        ax.set_xlim(0, 41)
axs[1, 0].set_xlabel("lag (days)"); axs[1, 1].set_xlabel("lag (days)")
save(fig, "acf")

# 8. AIC / BIC per family
best = {}
for c in M["candidates"]:
    f = c["family"]
    if f not in best or c["aic"] < best[f]["aic"]:
        best[f] = c
fams = list(best)
amin, bmin = min(best[f]["aic"] for f in fams), min(best[f]["bic"] for f in fams)
labels = [best[f]["label"].replace(" + Fourier", "\n+ Fourier") for f in fams]
fig, ax = plt.subplots(figsize=(11, 3.3))
yy = np.arange(len(fams))[::-1]; h = 0.38
da = [best[f]["aic"] - amin for f in fams]; db = [best[f]["bic"] - bmin for f in fams]
ax.barh(yy + h / 2, da, h, color=ACCENT, label="ΔAIC")
ax.barh(yy - h / 2, db, h, color=GREY, label="ΔBIC")
for y0, a, b, f in zip(yy, da, db, fams):
    ax.text(a + 4, y0 + h / 2, f"{a:.0f}  (AIC {best[f]['aic']:.0f})", va="center", fontsize=9.5, color=BODY)
    ax.text(b + 4, y0 - h / 2, f"{b:.0f}  (BIC {best[f]['bic']:.0f})", va="center", fontsize=9.5, color=MUTE)
ax.set_yticks(yy, labels, fontsize=10.5); ax.set_xlim(0, 480); ax.grid(axis="y", visible=False)
ax.set_xlabel("gap to the best model (0 = best; lower is better)"); ax.legend(loc="center right")
ax.set_title("Best order in each family, fitted on 2019–2023 (log AQI)")
save(fig, "aicbic")

# 9. Test RMSE by horizon
order = ["Naive", "Seasonal naive (7d)", "Holt-Winters ETS", "AR (10,0,0)", "MA (0,0,10)", "ARMA (3,0,3)",
         "ARIMA (2,1,3)", "SARIMA (3,0,3)(0,0,1)[7]", "SARIMAX-Fourier (3,0,0) + Fourier K=2"]
short = ["Naive", "S-naive", "ETS", "AR", "MA", "ARMA", "ARIMA", "SARIMA", "SARIMAX\n+Fourier"]
tm = {(m["model"], m["h"]): m for m in M["test_metrics"]}
fig, ax = plt.subplots(figsize=(11, 3.5))
xx = np.arange(len(order)); w = 0.27
for i, (h, col) in enumerate([(1, ACCENT), (3, "#5aa0f7"), (7, ACCENT_SOFT)]):
    ax.bar(xx + (i - 1) * w, [tm[(o, h)]["RMSE"] for o in order], w, color=col, label=f"{h}-day ahead")
ax.set_xticks(xx, short); ax.set_ylabel("RMSE (AQI points)"); ax.legend(ncols=3, loc="upper left")
ax.grid(axis="x", visible=False); ax.set_title("Mumbai, 2025 test year (365 rolling forecasts per horizon)")
save(fig, "rmse")

# 10. Actual vs forecast, AR(10) 1-day
p = M["test_paths"]["AR (10,0,0)"]["1"]
dt = pd.to_datetime(p["date"])
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.fill_between(dt, p["lo95"], p["hi95"], color=ACCENT_SOFT, alpha=0.6, lw=0, label="95% interval")
ax.plot(dt, p["actual"], color=INK, lw=1.0, label="Actual")
ax.plot(dt, p["forecast"], color=ACCENT, lw=1.2, label="AR(10) 1-day forecast")
ax.set_ylabel("AQI"); ax.legend(ncols=3, loc="upper center"); date_axis(ax, "%b")
ax.set_title("2025 out-of-sample: actual vs predicted")
save(fig, "actual_pred")

# 11. Residual diagnostics, AR(10)
dg = M["diagnostics"]["AR (10,0,0)"]
fig, axs = plt.subplots(1, 3, figsize=(12, 3.4))
rs = ts(dg["series"])
axs[0].plot(rs, color=ACCENT, lw=0.5); axs[0].set_title("Residuals over time"); date_axis(axs[0])
lags = np.arange(1, len(dg["acf"]))
axs[1].vlines(lags, 0, dg["acf"][1:], color=ACCENT, lw=1.6)
axs[1].axhspan(-dg["band"], dg["band"], color=ACCENT_SOFT, alpha=0.6, lw=0); axs[1].axhline(0, color=INK, lw=0.6)
axs[1].set_title("Residual ACF"); axs[1].set_xlabel("lag")
q = dg["qq"]
axs[2].scatter(q["theoretical"], q["sample"], s=6, color=ACCENT, lw=0)
lo, hi = min(q["theoretical"]), max(q["theoretical"])
axs[2].plot([lo, hi], [lo * dg["std"], hi * dg["std"]], color=INK, lw=0.8)
axs[2].set_title("Residual QQ plot")
save(fig, "resid")

# 12. Delhi vs Mumbai 7-day RMSE
dorder = ["Naive", "Holt-Winters ETS", "AR (10,0,0)", "ARMA (3,0,1)", "ARIMA (2,1,1)", "SARIMA (3,0,1)(0,0,1)[7]",
          "SARIMAX-Fourier (3,0,0) + Fourier K=4"]
dshort = ["Naive", "ETS", "AR", "ARMA", "ARIMA", "SARIMA", "SARIMAX\n+Fourier"]
dm = {(m["model"], m["h"]): m for m in D["test_metrics"]}
fig, ax = plt.subplots(figsize=(6.2, 3.6))
vals = [dm[(o, 7)]["RMSE"] for o in dorder]
ax.bar(dshort, vals, color=[GREY] + [ACCENT_SOFT] * 5 + [ACCENT])
for i, v in enumerate(vals):
    ax.text(i, v + 1, f"{v:.1f}", ha="center", fontsize=9)
ax.set_title("Delhi 2025: 7-day RMSE"); ax.grid(axis="x", visible=False); ax.tick_params(axis="x", labelsize=9)
save(fig, "delhi")

# Delhi line for context
sd = pd.Series(D["history"]["aqi"], index=pd.to_datetime(D["history"]["date"]), dtype=float)
fig, ax = plt.subplots(figsize=(6.2, 3.6))
ax.plot(sd["2018":].rolling(30, min_periods=20).mean(), color=INK, lw=1.4, label="Delhi")
ax.plot(s["2018":].rolling(30, min_periods=20).mean(), color=ACCENT, lw=1.4, label="Mumbai")
ax.set_title("30-day mean AQI"); ax.legend(); date_axis(ax)
save(fig, "cities")
print("figures:", sorted(p.name for p in OUT.glob("*.png")))
