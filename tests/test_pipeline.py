"""Fast sanity tests: chronology, imputation rules, no leakage in rolling forecasts, back-transform."""
import numpy as np
import pandas as pd

from src import data as dl
from src import evaluation as ev
from src import models as md


def toy(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    e = rng.normal(0, 0.1, n)
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = 0.7 * y[t - 1] + e[t]
    return pd.Series(np.exp(4.5 + y), index=idx)


def test_city_frame_is_daily_and_sorted():
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-03", "2020-01-01"]), "city": "X", "aqi": [100, 90],
                       "no_stations": 1, "aqi_category": "", "prominent_pollutant": ""})
    cf = dl.city_frame(df, "X")
    assert list(cf.index) == list(pd.date_range("2020-01-01", "2020-01-03"))
    assert cf["aqi"].isna().sum() == 1 and (cf["aqi"] == 0).sum() == 0


def test_impute_skips_long_gaps():
    s = toy(30)
    s.iloc[5:7] = np.nan      # 2-day gap -> filled
    s.iloc[15:20] = np.nan    # 5-day gap -> stays NaN
    out = dl.impute(s)
    assert out.iloc[5:7].notna().all()
    assert out.iloc[15:20].isna().all()


def test_rolling_forecast_uses_only_past():
    s = toy()
    y = np.log(s)
    spec = md.Spec("AR", "AR", (1, 0, 0))
    fc, _ = ev.rolling_forecasts(spec, y, "2020-12-01", "2020-12-10", "2021-01-31", 3)
    # Perturb data after an origin: forecasts made from that origin must not change.
    origin = pd.Timestamp("2020-12-20")
    y2 = y.copy(); y2[y2.index > origin] += 5
    fc2, _ = ev.rolling_forecasts(spec, y2, "2020-12-01", "2020-12-10", "2021-01-31", 3)
    a = fc[fc.origin == origin].forecast.values
    b = fc2[fc2.origin == origin].forecast.values
    assert np.allclose(a, b)
    assert (fc["date"] > fc["origin"]).all()


def test_back_transform_bounds():
    df = pd.DataFrame({"mean_log": [np.log(100), np.log(600)], "se_log": [0.2, 0.2]})
    out = ev.to_aqi_scale(df)
    assert np.isclose(out.forecast[0], 100)
    assert (out.hi95 <= 500).all() and (out.lo95 > 0).all()
    assert (out.lo95 <= out.lo80).all() and (out.hi80 <= out.hi95).all()
