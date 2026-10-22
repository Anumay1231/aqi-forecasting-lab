"""Builds notebooks/aqi_time_series_analysis.ipynb (run, then execute with nbconvert)."""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Forecasting Daily AQI in Mumbai: Applied Time Series Analysis

Walkthrough of the professor's 11-step workflow. Light steps are computed live here with the project's `src/` modules;
the order search and rolling-origin evaluation (a few minutes) are loaded from `artifacts/mumbai.json`, written by `run_pipeline.py` with the same code.
""")
code("""
import sys, json, warnings
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib.pyplot as plt, seaborn as sns
from scipy import stats
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from src import data as dl, analysis as an
from src.config import TRAIN_END, VAL_END
sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams["figure.figsize"] = (12, 4)
CITY, START = "Mumbai", "2019-01-01"
A = json.loads((ROOT / "artifacts" / "mumbai.json").read_text())
""")

md("## 1. Data collection")
code("""
raw = dl.load_raw()
cf = dl.city_frame(raw, CITY)
pd.Series(dl.data_card(raw, cf, CITY))
""")
code("""
raw.head()
""")
code("""
fig, ax = plt.subplots(1, 2, figsize=(14, 3.5))
cf["aqi"].plot(ax=ax[0], lw=0.6, color="k", title="Mumbai daily AQI, full history")
ax[0].axvspan(pd.Timestamp(START), cf.index[-1], color="tab:blue", alpha=0.08, label="model window")
ax[0].legend()
cf["no_stations"].groupby(cf.index.year).median().plot.bar(ax=ax[1], color="tab:blue", title="Median monitoring stations per year")
plt.tight_layout()
""")
md("Mumbai's city AQI came from one station until 2018 and from 7 to 24 afterwards, so the modelling window starts on 2019-01-01.")

md("## 3. Missing values")
code("""
pd.Series(dl.missingness_summary(cf, START)).drop(["missing_by_weekday"])
""")
code("""
pd.DataFrame(dl.compare_imputation(cf["aqi"][START:VAL_END]))
""")
code("""
s = dl.impute(cf["aqi"][START:], "time")   # gaps <= 3 days only, on the log scale
y = np.log(s)
print("remaining NaN:", s.isna().sum(), "| zero AQI values:", (s == 0).sum())
""")

md("## 2. Exploratory data analysis")
code("""
pd.Series(an.describe(s))
""")
code("""
fig, ax = plt.subplots(1, 3, figsize=(15, 3.8))
sns.histplot(s, bins=50, ax=ax[0]); ax[0].set_title("AQI distribution")
sns.histplot(y, bins=50, ax=ax[1], color="tab:orange"); ax[1].set_title("log AQI distribution")
stats.probplot(y, dist="norm", plot=ax[2]); ax[2].set_title("QQ plot, log AQI")
plt.tight_layout()
""")
code("""
fig, ax = plt.subplots(1, 3, figsize=(15, 3.8))
sns.boxplot(x=s.index.month, y=s.values, ax=ax[0], color="tab:blue"); ax[0].set(title="AQI by month", xlabel="month")
sns.boxplot(x=s.index.dayofweek, y=s.values, ax=ax[1], color="tab:gray"); ax[1].set(title="AQI by weekday (0 = Mon)", xlabel="")
ax[2].scatter(s.shift(1), s, s=3, alpha=0.4); ax[2].set(title=f"Lag-1 scatter, r = {s.autocorr(1):.2f}", xlabel="AQI(t-1)", ylabel="AQI(t)")
plt.tight_layout()
sp = an.seasonal_profiles(s)
print("Kruskal-Wallis p (month):", sp["kruskal_month_p"], "| (weekday):", round(sp["kruskal_weekday_p"], 3))
""")
code("""
out = an.outliers(s)
ax = s.plot(lw=0.6, color="gray", title=f"{len(out)} outliers flagged (robust z > 3.5); kept as real events")
ax.scatter(out.index, out["aqi"], color="red", s=20, zorder=3)
out.sort_values("robust_z", key=abs, ascending=False).head(10)
""")

md("## 4. Stationarity")
code("""
ytr, str_ = y[:TRAIN_END], s[:TRAIN_END]
r = an.rolling_stats(str_, 30)
ax = str_.plot(lw=0.5, color="lightgray", label="AQI"); r["mean"].plot(ax=ax, label="30-day mean"); r["std"].plot(ax=ax, label="30-day std"); ax.legend(); ax.set_title("Rolling statistics (training)")
""")
code("""
variants = {"AQI": str_, "log AQI": ytr, "diff log AQI": ytr.diff(), "seasonal diff (7)": ytr.diff(7)}
rows = an.stationarity_suite(variants)
pd.DataFrame([{"series": r["series"], "ADF stat": r["adf"]["statistic"], "ADF p": round(r["adf"]["p_value"], 4),
               "KPSS stat": r["kpss"]["statistic"], "KPSS p": r["kpss"]["p_value"], "verdict": r["verdict"]} for r in rows])
""")
md("ADF H0: unit root. KPSS H0: stationarity. Both agree that log AQI is stationary around its seasonal level (KPSS p is capped at 0.10 by statsmodels).")

md("## 5. Transformations")
code("""
print("Box-Cox lambda:", round(an.boxcox_lambda(str_), 3), "(0 = log)")
print(an.variance_by_level(str_))
""")
md("Lambda close to 0 and the drop in mean-variance correlation justify modelling log AQI. Forecasts are back-transformed with exp() (median) and capped at 500.")

md("## 6. Seasonality and decomposition")
code("""
dec = an.mstl_decompose(ytr)
fig, ax = plt.subplots(5, 1, figsize=(14, 10), sharex=True)
for a, c in zip(ax, ["observed", "trend", "seasonal_annual", "seasonal_weekly", "resid"]):
    dec[c].plot(ax=a, lw=0.7); a.set_ylabel(c)
dec["annual_fourier"].plot(ax=ax[2], color="k", lw=2)
plt.tight_layout()
an.seasonal_strength(dec)
""")

md("## 7. ACF and PACF")
code("""
fig, ax = plt.subplots(2, 2, figsize=(14, 6))
plot_acf(ytr, lags=40, ax=ax[0, 0], title="ACF log AQI"); plot_pacf(ytr, lags=40, ax=ax[0, 1], method="ywm", title="PACF log AQI")
plot_acf(ytr.diff().dropna(), lags=40, ax=ax[1, 0], title="ACF diff log AQI"); plot_pacf(ytr.diff().dropna(), lags=40, ax=ax[1, 1], method="ywm", title="PACF diff log AQI")
plt.tight_layout()
""")
md("Slow ACF decay with a PACF cut-off suggests AR structure on levels; the differenced series shows a negative lag-1 ACF, suggesting an MA term with d = 1.")

md("## 9 and 10. Lag selection, AIC and BIC (from the pipeline)")
code("""
cand = pd.DataFrame(A["candidates"])
pd.DataFrame({f: {"selected": v["label"]} for f, v in A["selected_orders"].items()}).T
""")
code("""
fig, ax = plt.subplots(1, 2, figsize=(14, 3.5))
for a, fam, i in [(ax[0], "AR", 0), (ax[1], "MA", 2)]:
    c = cand[cand.family == fam].assign(o=lambda d: d.order.str[i]).sort_values("o")
    a.plot(c.o, c.aic, "o-", label="AIC"); a.plot(c.o, c.bic, "s--", label="BIC"); a.set_title(f"{fam}: information criteria vs order"); a.legend()
cand.sort_values(["d_total", "aic"])[["family", "label", "d_total", "k_params", "loglik", "aic", "bic"]].head(15)
""")

md("## 8. Model comparison on the 2025 test year (rolling origin, 1 / 3 / 7 days ahead)")
code("""
tm = pd.DataFrame(A["test_metrics"])
print("Selected on 2024 validation:", A["selected_model"])
tm.pivot(index="model", columns="h", values="RMSE").sort_values(1).round(1)
""")
code("""
tm[tm.h == 1].sort_values("RMSE")[["model", "MAE", "RMSE", "MAPE", "sMAPE", "MASE", "cov80", "cov95", "category_acc"]]
""")
code("""
dm = pd.DataFrame(A["dm_tests"])
dm["p_one_sided_better"] = np.where(dm.stat < 0, dm.p_value / 2, 1 - dm.p_value / 2)
dm.pivot(index="model", columns="h", values="p_one_sided_better").round(4)
""")
code("""
sel = A["selected_model"]
fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
for a, h in zip(ax, ["1", "7"]):
    p = pd.DataFrame(A["test_paths"][sel][h]); p["date"] = pd.to_datetime(p.date)
    a.fill_between(p.date, p.lo95, p.hi95, alpha=0.2, label="95% PI"); a.plot(p.date, p.actual, "k", lw=1, label="actual"); a.plot(p.date, p.forecast, lw=1.2, label=f"{h}-day-ahead forecast")
    a.set_title(f"{sel}: {h}-day-ahead forecasts, 2025"); a.legend()
plt.tight_layout()
""")

md("## 11. Residual diagnostics (selected model)")
code("""
g = A["diagnostics"][sel]
r = pd.Series(g["series"]["value"], index=pd.to_datetime(g["series"]["date"]))
fig, ax = plt.subplots(1, 3, figsize=(15, 3.5))
r.plot(ax=ax[0], lw=0.5, title="residuals"); plot_acf(r, lags=40, ax=ax[1], title="residual ACF"); stats.probplot(r, plot=ax[2])
plt.tight_layout()
pd.DataFrame(g["ljung_box"]), g["jarque_bera"]
""")

md("""
## Deployment

`python -m uvicorn app.server:app --port 8000` serves the dashboard at http://localhost:8000. It uses the same trained parameters (`production` in the artifact) to forecast live, and exports CSV.

## Limitations

Univariate; heavy-tailed residuals; station network changes; evaluated up to 7 days ahead. Forecasts are study estimates, not official CPCB forecasts.
""")

nb["cells"] = C
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
out = Path(__file__).with_name("aqi_time_series_analysis.ipynb")
nbf.write(nb, out)
print("wrote", out)
