"""Requirements 8, 9, 10: model families, lag/order search, AIC/BIC.

All statistical models are fitted to y = log(AQI). Forecasts are back-transformed with exp()
(this gives the forecast median on the AQI scale) and intervals are exp() of log-scale bounds.
"""
import itertools
import warnings
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.exponential_smoothing.ets import ETSModel
from statsmodels.tsa.statespace.sarimax import SARIMAX

EPOCH = pd.Timestamp("2000-01-01")
YEAR = 365.25


@dataclass
class Spec:
    name: str
    family: str
    order: tuple = (0, 0, 0)
    seasonal_order: tuple = (0, 0, 0, 0)
    fourier_k: int = 0
    kind: str = "sarimax"  # sarimax | ets | naive | snaive
    params: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.kind != "sarimax":
            return self.name
        p, d, q = self.order
        s = f"({p},{d},{q})"
        if any(self.seasonal_order[:3]):
            P, D, Q, m = self.seasonal_order
            s += f"({P},{D},{Q})[{m}]"
        if self.fourier_k:
            s += f" + Fourier K={self.fourier_k}"
        return f"{self.name} {s}"

    def to_dict(self):
        d = asdict(self)
        d["label"] = self.label
        return d


def fourier(index: pd.DatetimeIndex, K: int, period: float = YEAR) -> pd.DataFrame | None:
    if K == 0:
        return None
    t = (index - EPOCH).days.values.astype(float)
    cols = {}
    for k in range(1, K + 1):
        cols[f"sin{k}"] = np.sin(2 * np.pi * k * t / period)
        cols[f"cos{k}"] = np.cos(2 * np.pi * k * t / period)
    return pd.DataFrame(cols, index=index)


def build(spec: Spec, y: pd.Series):
    """Create an (unfitted) statsmodels model for a spec on log-AQI series y."""
    if spec.kind == "ets":
        return ETSModel(y, error="add", trend="add", damped_trend=True,
                        seasonal="add", seasonal_periods=7)
    d = spec.order[1] + spec.seasonal_order[1]
    trend = "c" if d == 0 else "n"
    return SARIMAX(y, exog=fourier(y.index, spec.fourier_k), order=spec.order,
                   seasonal_order=spec.seasonal_order, trend=trend,
                   enforce_stationarity=True, enforce_invertibility=True)


def fit(spec: Spec, y: pd.Series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", UserWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        m = build(spec, y)
        if spec.kind == "ets":
            return m.fit(disp=False, maxiter=2000)
        return m.fit(disp=False, maxiter=200)


def refilter(spec: Spec, y: pd.Series, params):
    """Run an already-estimated model over a (longer) series with parameters held fixed."""
    m = build(spec, y)
    if spec.kind == "ets":
        return m.smooth(params)
    return m.filter(params)


def info_row(spec: Spec, res, n_eff: int | None = None) -> dict:
    return {
        "family": spec.family,
        "label": spec.label,
        "order": list(spec.order),
        "seasonal_order": list(spec.seasonal_order),
        "fourier_k": spec.fourier_k,
        "d_total": spec.order[1] + spec.seasonal_order[1],
        "k_params": int(len(res.params)),
        "loglik": round(float(res.llf), 2),
        "aic": round(float(res.aic), 2),
        "bic": round(float(res.bic), 2),
        "nobs": int(res.nobs),
    }


# ---------- order search (Requirement 9 + 10) ----------
def search(y: pd.Series, log=print) -> tuple[list, dict]:
    """Grid-search each family on the training series. Returns all candidate rows and the
    best spec per family (lowest AIC; BIC reported alongside)."""
    rows, best = [], {}

    def run(spec):
        try:
            r = fit(spec, y)
            row = info_row(spec, r)
            row["converged"] = bool(r.mle_retvals.get("converged", True)) if hasattr(r, "mle_retvals") and r.mle_retvals else True
            rows.append(row)
            cur = best.get(spec.family)
            if cur is None or row["aic"] < cur[1]:
                best[spec.family] = (spec, row["aic"])
            log(f"  {spec.label:45s} AIC={row['aic']:9.2f} BIC={row['bic']:9.2f}")
        except Exception as e:  # noqa: BLE001
            log(f"  {spec.label:45s} FAILED: {e}")

    for p in range(1, 15):
        run(Spec("AR", "AR", (p, 0, 0)))
    for q in range(1, 11):
        run(Spec("MA", "MA", (0, 0, q)))
    for p, q in itertools.product(range(1, 4), range(1, 4)):
        run(Spec("ARMA", "ARMA", (p, 0, q)))
    for p, q in itertools.product(range(0, 4), range(0, 4)):
        if p + q:
            run(Spec("ARIMA", "ARIMA", (p, 1, q)))

    arma = best["ARMA"][0].order
    arima = best["ARIMA"][0].order
    for base in (arma, arima):
        for P, Q in [(1, 0), (0, 1), (1, 1)]:
            run(Spec("SARIMA", "SARIMA", base, (P, 0, Q, 7)))
    run(Spec("SARIMA", "SARIMA", (arima[0], 1, arima[2]), (0, 1, 1, 7)))

    for K in range(1, 5):
        for p, q in [(1, 0), (2, 0), (1, 1), (2, 1), (3, 0)]:
            run(Spec("SARIMAX-Fourier", "SARIMAX-Fourier", (p, 0, q), fourier_k=K))

    best_specs = {f: s for f, (s, _) in best.items()}
    return rows, best_specs


def baseline_specs() -> list[Spec]:
    return [
        Spec("Naive", "Baseline", kind="naive"),
        Spec("Seasonal naive (7d)", "Baseline", kind="snaive"),
        Spec("Holt-Winters ETS", "Exponential smoothing", kind="ets"),
    ]


def spec_from_dict(d: dict) -> Spec:
    return Spec(name=d["name"], family=d["family"], order=tuple(d["order"]),
                seasonal_order=tuple(d["seasonal_order"]), fourier_k=d["fourier_k"],
                kind=d["kind"], params=d.get("params", {}))
