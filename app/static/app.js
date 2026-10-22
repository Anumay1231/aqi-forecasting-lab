"use strict";
/* AQI Forecasting Lab: every number on this page comes from artifacts/<city>.json
   (written by run_pipeline.py) or from the live /api/forecast endpoint. */

const S = { city: null, d: null, bands: [], fcModel: null, fcH: 7, testH: 1, testModel: null,
  diagModel: null, acfKey: "log AQI", valH: 1, aicFamily: "All", aicSort: ["aic", 1] };

const $ = (q, el = document) => el.querySelector(q);
const $$ = (q, el = document) => [...el.querySelectorAll(q)];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (x, d = 1) => (x === null || x === undefined || Number.isNaN(x)) ? "n/a" : Number(x).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtP = (p) => p < 0.001 ? "< 0.001" : fmt(p, 3);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;

function band(v) { for (const b of S.bands) if (v <= b[1]) return b; return S.bands[S.bands.length - 1]; }
function catChip(v) { const b = band(v); return `<span class="chip"><span class="dot" style="background:${b[3]}"></span>${b[2]}</span>`; }

/* ---------- plotting ---------- */
function baseLayout(extra = {}) {
  const ink = css("--ink"), mute = css("--mute"), grid = css("--plot-grid");
  const ax = { gridcolor: grid, zerolinecolor: grid, linecolor: css("--hairline-strong"), tickfont: { color: mute, size: 11 }, title: { font: { color: mute, size: 12 } } };
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: css("--font") || "system-ui", color: ink, size: 12 },
    margin: { l: 52, r: 16, t: 8, b: 40 }, hovermode: "x unified",
    hoverlabel: { bgcolor: css("--canvas"), bordercolor: css("--hairline-strong"), font: { color: ink, family: css("--mono"), size: 12 } },
    legend: { orientation: "h", y: 1.08, x: 0, font: { color: css("--body"), size: 12 }, bgcolor: "rgba(0,0,0,0)" },
    xaxis: { ...ax }, yaxis: { ...ax },
  }, extra, {
    xaxis: { ...ax, ...(extra.xaxis || {}) }, yaxis: { ...ax, ...(extra.yaxis || {}) },
  });
}
const CFG = { displayModeBar: false, responsive: true };
function plot(id, traces, layout = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!el.hasAttribute("role")) {
    const title = el.closest(".card")?.querySelector("h3")?.textContent || "Chart";
    el.setAttribute("role", "img"); el.setAttribute("aria-label", title);
  }
  Plotly.react(el, traces, baseLayout(layout), CFG);
}
const C = { ink: () => css("--ink"), accent: () => css("--accent"), mute: () => css("--series-2"), band: () => css("--plot-band"), band2: () => css("--plot-band-2") };

function bandShapes(ymax = 500, opacity = 0.07) {
  return S.bands.filter((b) => b[0] < ymax).map((b) => ({ type: "rect", xref: "paper", x0: 0, x1: 1, y0: b[0], y1: Math.min(b[1], ymax), fillcolor: b[3], opacity, line: { width: 0 }, layer: "below" }));
}

function acfBars(id, lags, vals, bandv, color) {
  const x = lags.slice(1), y = vals.slice(1);
  plot(id, [
    { type: "bar", x, y, marker: { color: y.map((v) => Math.abs(v) > bandv ? color : C.mute()) }, hovertemplate: "lag %{x}: %{y:.3f}<extra></extra>" },
  ], { hovermode: "closest", bargap: 0.35, showlegend: false, xaxis: { title: { text: "lag (days)" } },
    shapes: [bandv, -bandv].map((b) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: b, y1: b, line: { color: C.accent(), dash: "dot", width: 1 } })) });
}

/* ---------- UI helpers ---------- */
function seg(name, options, current) {
  return `<div class="t-tabs" role="tablist" data-seg="${name}"><span class="t-tabs-pill" aria-hidden="true"></span>${options.map(([v, l]) => `<button type="button" class="t-tab" role="tab" data-v="${v}" aria-selected="${String(v) === String(current)}">${l}</button>`).join("")}</div>`;
}
function select(id, options, current, label) {
  return `<div class="control"><label for="${id}">${label}</label><select id="${id}">${options.map((o) => `<option value="${esc(o)}" ${o === current ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
}
function stat(k, v, s = "", key = "") { return `<div class="stat"><div class="k">${k}</div><div class="v">${key ? `<span class="t-digit-group" data-key="${key}">${v}</span>` : v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`; }
function head(num, title, lede) {
  return `<div class="sec-head">${num ? `<span class="sec-num">${num}</span>` : ""}${num === "11" ? `<h1>${title}</h1>` : `<h2>${title}</h2>`}</div><p class="lede">${lede}</p>`;
}
function table(cols, rows, opts = {}) {
  const th = cols.map((c) => `<th class="${c.num ? "num" : ""}" scope="col">${c.sort ? `<button type="button" class="sort-btn" data-sort="${c.key}" aria-label="Sort by ${c.label}">${c.label}</button>` : c.label}</th>`).join("");
  const tr = rows.map((r) => `<tr class="${opts.hl && opts.hl(r) ? "hl" : ""}">${cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="${opts.wrap ? "wrap" : ""}"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/* ---------- sections ---------- */
function models() { return Object.keys(S.d.production); }
function testRow(model, h) { return S.d.test_metrics.find((r) => r.model === model && r.h === h); }

function secForecast() {
  const d = S.d, sel = d.selected_model, h1 = testRow(sel, 1), nv = testRow("Naive", 1);
  const gain = (1 - h1.RMSE / nv.RMSE) * 100;
  const last = d.history.aqi.filter((v) => v !== null).slice(-1)[0];
  return `<section id="forecast">
    ${head("11", `${esc(d.city)} daily AQI forecast`, `Short-range estimates of the CPCB city AQI from classical time series models, trained on ${d.model_start.slice(0, 4)} to ${d.last_observation.slice(0, 4)} bulletins.`)}
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row">
      ${stat("Last observed", `${fmt(last, 0)}`, `${catChip(last)} &nbsp;on ${d.last_observation}`, "last")}
      ${stat("Selected model", `<span style="font-size:16px;line-height:22px;letter-spacing:-.3px;display:block">${esc(sel)}</span>`, "lowest mean validation RMSE (2024)")}
      ${stat("Test RMSE, 1 day", fmt(h1.RMSE, 1), `${gain >= 0 ? "" : "+"}${fmt(Math.abs(gain), 0)}% ${gain >= 0 ? "below" : "above"} naive (${fmt(nv.RMSE, 1)})`, "rmse")}
      ${stat("95% interval coverage", `${fmt(h1.cov95, 0)}%`, "share of 2025 days inside the band", "cov")}
    </div></div>
    <div class="grid g-hero">
      <div class="card">
        <div class="controls">
          ${select("fc-model", models(), S.fcModel, "Model")}
          <div class="control"><label for="fc-h">Horizon</label><div class="range-wrap"><input type="range" id="fc-h" min="1" max="30" value="${S.fcH}"><output id="fc-h-out">${S.fcH} days</output></div></div>
          <div class="control"><label>&nbsp;</label><a class="btn btn-primary" id="fc-csv" href="#">Download CSV</a></div>
        </div>
        <div id="fc-chart" class="chart tall"></div>
        <p class="disclaimer" id="fc-note"></p>
      </div>
      <div class="card flush"><div style="padding:16px 20px 8px"><h3>Forecast table</h3><p class="muted" style="margin:0;font-size:13px">Median forecast with 95% prediction interval</p></div><div id="fc-table" aria-live="polite"></div></div>
    </div>
    <p class="disclaimer">Statistical estimates for study purposes. Not an official CPCB forecast, warning, or medical advice.</p>
  </section>`;
}

async function drawForecast() {
  const q = new URLSearchParams({ city: S.city, model: S.fcModel, h: S.fcH });
  $("#fc-csv").href = `/api/forecast.csv?${q}`;
  const tableEl = $("#fc-table");
  tableEl.innerHTML = `<div class="skeleton" style="height:240px;margin:12px 20px"></div>`;
  let r;
  try {
    const res = await fetch(`/api/forecast?${q}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    r = await res.json();
  } catch (e) { tableEl.innerHTML = `<div class="error-box" style="margin:12px 20px">Forecast failed: ${esc(e.message)}</div>`; return; }
  const f = r.forecast, hx = r.history;
  const ymax = Math.min(500, Math.max(...hx.aqi, ...f.hi95) * 1.08);
  plot("fc-chart", [
    { x: [...f.date, ...[...f.date].reverse()], y: [...f.hi95, ...[...f.lo95].reverse()], mode: "lines", fill: "toself", fillcolor: C.band(), line: { width: 0 }, name: "95% interval", hoverinfo: "skip" },
    { x: [...f.date, ...[...f.date].reverse()], y: [...f.hi80, ...[...f.lo80].reverse()], mode: "lines", fill: "toself", fillcolor: C.band2(), line: { width: 0 }, name: "80% interval", hoverinfo: "skip" },
    { x: hx.date, y: hx.aqi, name: "Observed", line: { color: C.ink(), width: 1.6 }, hovertemplate: "%{y:.0f}" },
    { x: [hx.date[hx.date.length - 1], ...f.date], y: [hx.aqi[hx.aqi.length - 1], ...f.forecast], name: "Forecast", line: { color: C.accent(), width: 2.2 }, mode: "lines+markers", marker: { size: 5 }, hovertemplate: "%{y:.0f}" },
  ], { yaxis: { title: { text: "AQI" }, range: [0, ymax] }, shapes: [...bandShapes(ymax), { type: "line", x0: hx.date[hx.date.length - 1], x1: hx.date[hx.date.length - 1], yref: "paper", y0: 0, y1: 1, line: { color: css("--hairline-strong"), dash: "dot", width: 1 } }] });
  tableEl.innerHTML = table([
    { key: "date", label: "Date" }, { key: "forecast", label: "AQI", num: true, fmt: (v) => fmt(v, 0) },
    { key: "pi", label: "95% PI", num: true }, { key: "category", label: "Category", fmt: (v, row) => catChip(row.forecast) },
  ], f.date.map((d, i) => ({ date: d, forecast: f.forecast[i], pi: `${fmt(f.lo95[i], 0)} to ${fmt(f.hi95[i], 0)}`, category: f.category[i] })));
  $("#fc-note").textContent = S.fcH > 7
    ? `Accuracy was only evaluated up to 7 days ahead. Beyond that the forecast converges to the model's seasonal mean and intervals widen.`
    : `Intervals come from the model's own forecast variance on the log scale, transformed back to AQI.`;
}

function secData() {
  const d = S.d, c = d.data_card, src = d.source;
  return `<section id="data">
    ${head("01", "Data collection", "Daily city AQI from Central Pollution Control Board bulletins, compiled into one table by UrbanEmissions.info.")}
    <div class="grid g2">
      <div class="card"><h3>Data card</h3><dl class="kv" style="margin-top:12px">
        <dt>source</dt><dd><a href="${src.original}" target="_blank" rel="noopener">CPCB daily AQI bulletin</a> via <a href="${src.repo}" target="_blank" rel="noopener">AQI_bulletins</a></dd>
        <dt>file</dt><dd class="mono">${esc(src.file)}</dd>
        <dt>license</dt><dd>${esc(src.license)}</dd>
        <dt>coverage</dt><dd>${c.date_min} to ${c.date_max}, ${c.n_cities} cities, ${fmt(c.rows_all_cities, 0)} rows</dd>
        <dt>columns</dt><dd class="mono">${c.columns.join(", ")}</dd>
        <dt>frequency</dt><dd>${esc(c.frequency)}</dd>
        <dt>units</dt><dd>${esc(c.units)}</dd>
        <dt>${esc(d.city)}</dt><dd>${c.city_first} to ${c.city_last}, ${fmt(c.city_observed_days, 0)} observed of ${fmt(c.city_calendar_days, 0)} days</dd>
        <dt>duplicates</dt><dd>${c.duplicates_city_date} city-date duplicates, ${c.zero_aqi_values} zero values</dd>
        <dt>model window</dt><dd>${d.splits.train[0]} onward. Train to ${d.splits.train[1]}, validate on 2024, test on 2025</dd>
      </dl></div>
      <div class="card"><div class="card-head"><h3>Monitoring stations per year</h3></div><div id="ch-stations" class="chart short"></div>
        <p id="txt-stations" style="margin-bottom:0"></p></div>
    </div>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>Full history</h3><p class="muted">Shaded region is the modelling window</p></div><div id="ch-history" class="chart"></div></div>
  </section>`;
}
function drawData() {
  const d = S.d, yrs = Object.keys(d.stations_by_year), st = Object.values(d.stations_by_year);
  plot("ch-stations", [{ type: "bar", x: yrs, y: st, marker: { color: yrs.map((y) => +y >= +d.model_start.slice(0, 4) ? C.accent() : C.mute()) }, hovertemplate: "%{x}: %{y} stations<extra></extra>" }], { hovermode: "closest", yaxis: { title: { text: "median stations" } } });
  const first = st[0], startYear = d.model_start.slice(0, 4);
  $("#txt-stations").innerHTML = `City AQI is the average over reporting stations. ${esc(d.city)} went from ${first} station${first === 1 ? "" : "s"} in ${yrs[0]} to ${st[st.length - 1]} in ${yrs[yrs.length - 1]}. Early values measure something different, so modelling starts in ${startYear}.`;
  plot("ch-history", [{ x: d.history.date, y: d.history.aqi, line: { color: C.ink(), width: 1 }, name: "AQI", connectgaps: false, hovertemplate: "%{y:.0f}<extra></extra>" }],
    { showlegend: false, yaxis: { title: { text: "AQI" } }, shapes: [{ type: "rect", x0: d.model_start, x1: d.last_observation, yref: "paper", y0: 0, y1: 1, fillcolor: C.band(), line: { width: 0 }, layer: "below" }] });
}

function secEDA() {
  const e = S.d.eda, ds = e.describe_window, sp = e.seasonal;
  const mo = sp.month, hi = mo.reduce((a, b) => a.mean > b.mean ? a : b), lo = mo.reduce((a, b) => a.mean < b.mean ? a : b);
  return `<section id="eda">
    ${head("02", "Exploratory analysis", `Modelling window ${S.d.model_start} to ${S.d.last_observation}. Distribution, seasonality, persistence and unusual days.`)}
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row">
      ${stat("Mean", fmt(ds.mean, 1), `median ${fmt(ds["50%"], 0)}`)}
      ${stat("Std dev", fmt(ds.std, 1), `IQR ${fmt(ds["25%"], 0)} to ${fmt(ds["75%"], 0)}`)}
      ${stat("Range", `${fmt(ds.min, 0)} to ${fmt(ds.max, 0)}`, `${fmt(ds.count, 0)} days`)}
      ${stat("Skewness", fmt(ds.skewness, 2), `log scale ${fmt(ds.log_skewness, 2)}`)}
    </div></div>
    <div class="grid g2">
      <div class="card"><div class="card-head"><h3>Distribution</h3>${seg("hist", [["raw", "AQI"], ["log", "log AQI"]], "raw")}</div><div id="ch-hist" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>QQ plot against normal</h3></div><div id="ch-qq" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>Monthly profile</h3><p class="mono muted">Kruskal-Wallis p ${fmtP(sp.kruskal_month_p)}</p></div><div id="ch-month" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>Weekday profile</h3><p class="mono muted">Kruskal-Wallis p ${fmtP(sp.kruskal_weekday_p)}</p></div><div id="ch-week" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>Persistence: AQI today vs yesterday</h3><p class="mono muted">r₁ ${fmt(e.lag_scatter.corr_lag1, 2)} · r₇ ${fmt(e.lag_scatter.corr_lag7, 2)} · r₃₆₅ ${fmt(e.lag_scatter.corr_lag365, 2)}</p></div><div id="ch-lag" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>Prominent pollutant</h3></div><div id="ch-poll" class="chart short"></div></div>
    </div>
    <div class="callout"><strong>Reading.</strong> AQI peaks in ${MONTHS[hi.month - 1]} (mean ${fmt(hi.mean, 0)}) and bottoms out in ${MONTHS[lo.month - 1]} (mean ${fmt(lo.mean, 0)}) during the monsoon, so annual seasonality dominates. The distribution is right-skewed (skew ${fmt(ds.skewness, 2)}); a log transform brings it to ${fmt(ds.log_skewness, 2)}. Strong day-to-day persistence (r₁ = ${fmt(e.lag_scatter.corr_lag1, 2)}) is what autoregressive models exploit.</div>
    <div class="grid g2" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr)">
      <div class="card"><div class="card-head"><h3>Outlier inspection</h3><p class="muted">Robust z-score above 3.5 against a 30-day rolling median on log AQI</p></div><div id="ch-out" class="chart"></div></div>
      <div class="card flush"><div style="padding:16px 20px 8px"><h3>${e.outliers.length} flagged days</h3><p class="muted" style="margin:0;font-size:13px">Kept in the data; spikes are real pollution events</p></div>
        ${table([{ key: "date", label: "Date" }, { key: "aqi", label: "AQI", num: true, fmt: (v) => fmt(v, 0) }, { key: "robust_z", label: "z", num: true, fmt: (v) => fmt(v, 1) }], [...e.outliers].sort((a, b) => Math.abs(b.robust_z) - Math.abs(a.robust_z)).slice(0, 9))}</div>
    </div>
  </section>`;
}
function drawEDA(histMode = "raw") {
  const e = S.d.eda, vals = e.values_window;
  const xs = histMode === "raw" ? vals : vals.map(Math.log);
  plot("ch-hist", [{ type: "histogram", x: xs, nbinsx: 50, marker: { color: C.accent(), line: { color: css("--canvas"), width: 0.5 } }, hovertemplate: "%{x}: %{y} days<extra></extra>" }], { hovermode: "closest", bargap: 0.02, xaxis: { title: { text: histMode === "raw" ? "AQI" : "log AQI" } }, yaxis: { title: { text: "days" } } });
  const qq = (k, name, color) => ({ x: e[k].theoretical, y: e[k].sample, mode: "markers", name, marker: { size: 4, color } });
  plot("ch-qq", [qq("qq_raw", "AQI", C.mute()), qq("qq_log", "log AQI", C.accent()), { x: [-3.5, 3.5], y: [-3.5, 3.5], mode: "lines", line: { color: C.ink(), dash: "dot", width: 1 }, name: "normal", hoverinfo: "skip" }],
    { hovermode: "closest", xaxis: { title: { text: "theoretical quantile" } }, yaxis: { title: { text: "standardised sample" } } });
  const mo = S.d.eda.seasonal.month;
  plot("ch-month", [{ type: "bar", x: mo.map((m) => MONTHS[m.month - 1]), y: mo.map((m) => m.mean), error_y: { type: "data", array: mo.map((m) => m.std), color: css("--hairline-strong"), thickness: 1 }, marker: { color: mo.map((m) => band(m.mean)[3]) }, hovertemplate: "%{x}: mean %{y:.0f}<extra></extra>" }], { hovermode: "closest", yaxis: { title: { text: "mean AQI ± sd" } } });
  const wd = S.d.eda.seasonal.weekday;
  plot("ch-week", [{ type: "bar", x: wd.map((m) => DAYS[m.weekday]), y: wd.map((m) => m.mean), marker: { color: C.accent() }, hovertemplate: "%{x}: mean %{y:.1f}<extra></extra>" }], { hovermode: "closest", yaxis: { title: { text: "mean AQI" } } });
  plot("ch-lag", [{ type: "scattergl", x: e.lag_scatter.x, y: e.lag_scatter.y, mode: "markers", marker: { size: 3, color: C.accent(), opacity: 0.45 }, hoverinfo: "skip" }, { x: [0, 500], y: [0, 500], mode: "lines", line: { color: C.ink(), dash: "dot", width: 1 }, hoverinfo: "skip" }],
    { showlegend: false, hovermode: false, xaxis: { title: { text: "AQI yesterday" }, range: [0, Math.max(...e.lag_scatter.x) * 1.05] }, yaxis: { title: { text: "AQI today" }, range: [0, Math.max(...e.lag_scatter.y) * 1.05] } });
  const pk = Object.keys(e.pollutants).reverse(), pv = Object.values(e.pollutants).reverse();
  plot("ch-poll", [{ type: "bar", orientation: "h", y: pk, x: pv, marker: { color: C.accent() }, hovertemplate: "%{y}: %{x} days<extra></extra>" }], { hovermode: "closest", margin: { l: 120, r: 16, t: 8, b: 40 }, xaxis: { title: { text: "days" } } });
  const h = S.d.history, i0 = h.date.indexOf(S.d.model_start);
  plot("ch-out", [
    { x: h.date.slice(i0), y: h.aqi.slice(i0), line: { color: C.mute(), width: 1 }, name: "AQI", hovertemplate: "%{y:.0f}<extra></extra>" },
    { x: e.outliers.map((o) => o.date), y: e.outliers.map((o) => o.aqi), mode: "markers", name: "flagged", marker: { color: css("--danger"), size: 7, symbol: "circle-open", line: { width: 2 } }, hovertemplate: "%{x}: %{y:.0f}<extra>flagged</extra>" },
  ], { yaxis: { title: { text: "AQI" } } });
}

function secMissing() {
  const m = S.d.missing, imp = S.d.imputation_comparison, best = imp.reduce((a, b) => a.mae < b.mae ? a : b);
  const gaps = Object.entries(m.full_gap_length_counts).map(([k, v]) => `${v}×${k}d`).join(", ");
  return `<section id="missing">
    ${head("03", "Missing values", "Missing days are rebuilt as explicit NaN rows on a daily calendar, so they are never confused with zero AQI.")}
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row">
      ${stat("Full history", `${fmt(m.full_missing_pct, 1)}%`, `${m.full_missing_days} missing days`)}
      ${stat("Longest gap", `${m.full_longest_gap} days`, "full history")}
      ${stat("Model window", `${m.window_missing_days} days`, `${fmt(m.window_missing_pct, 2)}% · longest ${m.window_longest_gap} d`)}
      ${stat("After imputation", m.after_imputation, "remaining NaN in window")}
    </div></div>
    <div class="grid g2">
      <div class="card"><div class="card-head"><h3>Missing days per year</h3></div><div id="ch-miss" class="chart short"></div></div>
      <div class="card flush"><div style="padding:16px 20px 8px"><h3>Imputation methods compared</h3><p class="muted" style="margin:0;font-size:13px">Known values hidden in random 1 to 3 day blocks, then rebuilt</p></div>
        ${table([{ key: "method", label: "Method", fmt: (v) => ({ time: "Time interpolation (log)", ffill: "Forward fill", weekly: "Same weekday last week" }[v]) }, { key: "mae", label: "MAE (AQI)", num: true, fmt: (v) => fmt(v, 2) }, { key: "n_blocks", label: "Blocks", num: true }], imp, { hl: (r) => r.method === best.method })}</div>
    </div>
    <div class="callout"><strong>Decision.</strong> Gaps in the window are short (${m.window_missing_dates.join(", ") || "none"}). ${({ time: "Time interpolation on the log scale", ffill: "Forward fill", weekly: "Weekly fill" })[best.method]} had the lowest reconstruction error (${fmt(best.mae, 1)} AQI), and is applied only to gaps of 3 days or less. Longer gaps would stay NaN; the state-space models handle them through the Kalman filter instead of inventing data. Full-history gap lengths: ${gaps}.</div>
  </section>`;
}
function drawMissing() {
  const m = S.d.missing.missing_by_year;
  plot("ch-miss", [{ type: "bar", x: Object.keys(m), y: Object.values(m), marker: { color: Object.keys(m).map((y) => +y >= +S.d.model_start.slice(0, 4) ? C.accent() : C.mute()) }, hovertemplate: "%{x}: %{y} days<extra></extra>" }], { hovermode: "closest", yaxis: { title: { text: "missing days" } } });
}

function verdictChip(v) { const cls = v === "stationary" ? "ok" : v === "non-stationary" ? "bad" : ""; return `<span class="chip ${cls}">${esc(v)}</span>`; }
function secStationarity() {
  const rows = S.d.stationarity;
  return `<section id="stationarity">
    ${head("04", "Stationarity", "A stationary series has a constant mean, variance and autocorrelation over time. ARMA-type models assume it, so we test before modelling.")}
    <div class="card"><div class="card-head"><h3>Rolling 30-day mean and standard deviation (training data)</h3></div><div id="ch-roll" class="chart"></div></div>
    <div class="card flush" style="margin-top:16px">
      ${table([
        { key: "series", label: "Series" },
        { key: "adf", label: "ADF stat", num: true, fmt: (v) => fmt(v.statistic, 2) },
        { key: "adf", label: "ADF p", num: true, fmt: (v) => fmtP(v.p_value) },
        { key: "adf", label: "lags", num: true, fmt: (v) => v.lags_used },
        { key: "kpss", label: "KPSS stat", num: true, fmt: (v) => fmt(v.statistic, 3) },
        { key: "kpss", label: "KPSS p", num: true, fmt: (v) => (v.p_value <= 0.01 ? "≤ 0.01" : v.p_value >= 0.1 ? "≥ 0.10" : fmt(v.p_value, 3)) },
        { key: "verdict", label: "Verdict", fmt: verdictChip },
      ], rows)}
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h3>ADF (Augmented Dickey-Fuller)</h3><p>H₀: the series has a unit root (non-stationary). A p-value below 0.05 rejects H₀. 5% critical value for log AQI: ${fmt(rows[1].adf.critical_values["5%"], 2)}.</p></div>
      <div class="card"><h3>KPSS (complementary)</h3><p>H₀ is reversed: the series is level-stationary. A p-value below 0.05 rejects stationarity. Using both tests guards against the low power of either alone.</p></div>
    </div>
    <div class="callout" id="txt-stat"></div>
  </section>`;
}
function drawStationarity() {
  const r = S.d.rolling, rows = S.d.stationarity, lg = rows[1];
  plot("ch-roll", [
    { x: r.aqi_mean.date, y: r.aqi_mean.value, name: "rolling mean", line: { color: C.ink(), width: 1.6 } },
    { x: r.aqi_std.date, y: r.aqi_std.value, name: "rolling std", line: { color: C.accent(), width: 1.6 }, yaxis: "y2" },
  ], { yaxis: { title: { text: "mean AQI" } }, yaxis2: { overlaying: "y", side: "right", title: { text: "std", font: { color: css("--mute"), size: 12 } }, tickfont: { color: css("--mute"), size: 11 }, gridcolor: "rgba(0,0,0,0)" }, margin: { l: 52, r: 52, t: 8, b: 40 } });
  const dl = rows[2], kp = lg.kpss.p_value >= 0.1 ? "≥ 0.10" : lg.kpss.p_value <= 0.01 ? "≤ 0.01" : fmt(lg.kpss.p_value, 2);
  const body = lg.verdict === "stationary"
    ? `Both tests agree that log AQI is stationary: the series keeps returning to its seasonal level instead of drifting like a random walk. The rolling mean still swings with the seasons, so the stationarity is <em>around a repeating seasonal pattern</em>, which seasonal or Fourier terms should capture. Levels models (d = 0: AR, MA, ARMA, SARIMAX-Fourier) are therefore justified. ARIMA with d = 1 is still fitted to check empirically whether differencing helps; on the differenced series the tests also agree (${dl.verdict}).`
    : `The verdict is <em>${lg.verdict}</em>. Mixed results usually mean a mean-reverting series with strong deterministic seasonality rather than a pure random walk. After first differencing: ${dl.verdict}. We compare both routes: levels with seasonal terms (d = 0) and differencing (d = 1).`;
  $("#txt-stat").innerHTML = `<strong>Conclusion.</strong> For log AQI, ADF gives p ${fmtP(lg.adf.p_value)} (reject unit root) and KPSS gives p ${kp}. ${body}`;
}

function secTransform() {
  const t = S.d.transform;
  return `<section id="transform">
    ${head("05", "Transformations", "Variance grows with the level of pollution. A log transform stabilises it and keeps forecasts positive when transformed back.")}
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row">
      ${stat("Box-Cox λ", fmt(t.boxcox_lambda, 2), "λ = 0 is the log transform")}
      ${stat("corr(mean, std), raw", fmt(t.corr_mean_std_raw, 2), "monthly mean vs monthly std")}
      ${stat("corr(mean, std), log", fmt(t.corr_mean_std_log, 2), "after log transform")}
    </div></div>
    <div class="card"><div class="card-head"><h3>Rolling 30-day statistics of log AQI</h3></div><div id="ch-logroll" class="chart short"></div></div>
    <div class="callout"><strong>Decision.</strong> Box-Cox estimates λ = ${fmt(t.boxcox_lambda, 2)}, close to 0, so we use the simpler and interpretable log. The mean-variance correlation moves from ${fmt(t.corr_mean_std_raw, 2)} to ${fmt(t.corr_mean_std_log, 2)}. All models are fitted to log AQI; forecasts are back-transformed with exp(), which gives the median AQI, and interval bounds are transformed the same way, then capped at the AQI ceiling of 500. Differencing (d = 1, and seasonal D = 1 at lag 7) is tested in section 04 and applied inside ARIMA and SARIMA candidates, where the model integrates the forecast back automatically.</div>
  </section>`;
}
function drawTransform() {
  const r = S.d.rolling;
  plot("ch-logroll", [
    { x: r.log_mean.date, y: r.log_mean.value, name: "rolling mean", line: { color: C.ink(), width: 1.6 } },
    { x: r.log_std.date, y: r.log_std.value, name: "rolling std", line: { color: C.accent(), width: 1.6 }, yaxis: "y2" },
  ], { yaxis: { title: { text: "mean log AQI" } }, yaxis2: { overlaying: "y", side: "right", tickfont: { color: css("--mute"), size: 11 }, gridcolor: "rgba(0,0,0,0)" }, margin: { l: 52, r: 52, t: 8, b: 40 } });
}

function secDecomp() {
  const s = S.d.decomposition.strength;
  return `<section id="decomposition">
    ${head("06", "Seasonality and decomposition", "MSTL splits log AQI into trend, weekly (period 7) and annual (period 365) seasonality, and a residual.")}
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row">
      ${stat("Annual strength", fmt(s.annual_strength, 2), "0 = none, 1 = dominant")}
      ${stat("Weekly strength", fmt(s.weekly_strength, 2), "")}
      ${stat("Trend strength", fmt(s.trend_strength, 2), "")}
    </div></div>
    <div class="card"><div class="card-head"><h3>MSTL decomposition of log AQI (training data)</h3><p class="muted">Periods chosen from the data's daily frequency and the profiles in section 02</p></div><div id="ch-mstl" class="chart xtall"></div></div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>Classical multiplicative decomposition, monthly means</h3></div><div id="ch-classic" class="chart short"></div></div>
      <div class="card"><h3>Why these periods</h3><p>Daily data supports weekly and annual cycles. A 365-day seasonal ARIMA is computationally impractical (365 seasonal lags), so annual seasonality is modelled with Fourier terms instead, and SARIMA handles the weekly cycle. Classical decomposition on monthly means (period 12) is shown as a cross-check; it assumes a fixed seasonal shape and loses the first and last six months to its moving average.</p><p id="txt-decomp" style="margin-bottom:0"></p></div>
    </div>
  </section>`;
}
function drawDecomp() {
  const d = S.d.decomposition, comps = [["observed", "observed"], ["trend", "trend"], ["seasonal_annual", "annual"], ["seasonal_weekly", "weekly"], ["resid", "residual"]];
  const n = comps.length, gap = 0.04, h = (1 - gap * (n - 1)) / n;
  const traces = comps.map(([k, name], i) => ({ x: d[k].date, y: d[k].value, name, xaxis: "x", yaxis: `y${i ? i + 1 : ""}`, line: { color: i === 0 ? C.ink() : C.accent(), width: k === "seasonal_weekly" ? 0.8 : 1.2 }, hovertemplate: "%{y:.3f}" }));
  const lay = { showlegend: false, margin: { l: 60, r: 16, t: 8, b: 32 }, xaxis: { anchor: `y${n}` } };
  comps.forEach(([, name], i) => {
    const top = 1 - i * (h + gap);
    lay[`yaxis${i ? i + 1 : ""}`] = { domain: [top - h, top], title: { text: name }, gridcolor: css("--plot-grid"), zerolinecolor: css("--plot-grid"), tickfont: { color: css("--mute"), size: 10 }, title_font: { size: 11 } };
  });
  if (d.annual_fourier) traces.push({ x: d.annual_fourier.date, y: d.annual_fourier.value, name: "smooth annual (Fourier K=3)", xaxis: "x", yaxis: "y3", line: { color: C.ink(), width: 2.4 }, hovertemplate: "%{y:.3f}" });
  plot("ch-mstl", traces, lay);
  const c = S.d.classical_monthly.seasonal;
  const first12 = c.value.slice(0, 12), months = c.date.slice(0, 12).map((x) => MONTHS[+x.slice(5, 7) - 1]);
  plot("ch-classic", [{ type: "bar", x: months, y: first12, marker: { color: first12.map((v) => v >= 1 ? css("--danger") : C.accent()) }, hovertemplate: "%{x}: ×%{y:.2f}<extra></extra>" }],
    { hovermode: "closest", yaxis: { title: { text: "seasonal factor" } }, shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1, line: { color: C.ink(), dash: "dot", width: 1 } }] });
  const mx = Math.max(...first12), mn = Math.min(...first12);
  $("#txt-decomp").innerHTML = `Monthly factors range from ×${fmt(mn, 2)} (${months[first12.indexOf(mn)]}) to ×${fmt(mx, 2)} (${months[first12.indexOf(mx)]}): the cleanest month averages about ${fmt((1 - mn) * 100, 0)}% below the yearly level, the worst ${fmt((mx - 1) * 100, 0)}% above.`;
}

function secACF() {
  const keys = Object.keys(S.d.acf_pacf).filter((k) => !k.includes("long"));
  return `<section id="acf">
    ${head("07", "ACF and PACF", "Autocorrelation measures how today relates to each past day; partial autocorrelation removes the effect of the days in between.")}
    <div class="controls">${seg("acf", keys.map((k) => [k, k]), S.acfKey)}</div>
    <div class="grid g2">
      <div class="card"><div class="card-head"><h3>ACF</h3><p class="mono muted">dotted lines: ±1.96/√n</p></div><div id="ch-acf" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>PACF</h3></div><div id="ch-pacf" class="chart short"></div></div>
    </div>
    <div class="callout" id="txt-acf"></div>
    <div class="card"><div class="card-head"><h3>ACF of log AQI out to 400 lags</h3><p class="muted">The wave peaking near lag 365 is the annual cycle</p></div><div id="ch-acflong" class="chart short"></div></div>
  </section>`;
}
function drawACF() {
  const a = S.d.acf_pacf[S.acfKey];
  acfBars("ch-acf", a.lags, a.acf, a.band, C.accent());
  acfBars("ch-pacf", a.lags, a.pacf, a.band, C.accent());
  const sp = a.significant_pacf_lags.filter((l) => l <= 14), sa = a.significant_acf_lags;
  const guide = {
    "log AQI": `The ACF decays slowly over all ${a.lags.length - 1} lags while the PACF cuts off after a few lags (significant: ${sp.join(", ") || "none"} within two weeks). That pattern points to an autoregressive structure, suggesting AR orders around ${Math.max(...sp.filter((l) => l <= 10), 1)} and modest ARMA orders.`,
    "Δ log AQI": `After differencing, the lag-1 ACF is negative (${fmt(a.acf[1], 2)}) and the ACF cuts off quickly, the signature of an MA term in an ARIMA(p,1,q) model. Spikes at lags ${sa.filter((l) => l % 7 === 0).slice(0, 3).join(", ") || "none"} hint at weekly seasonality.`,
    "MSTL residual": `Even after removing trend and both seasonal cycles, short lags stay significant (${a.significant_acf_lags.slice(0, 6).join(", ")}). Seasonality alone is not enough; the remainder still needs ARMA dynamics, which motivates seasonal terms plus ARMA errors.`,
  }[S.acfKey];
  $("#txt-acf").innerHTML = `<strong>Interpretation.</strong> ${guide} ACF and PACF only suggest candidate orders; the final choice is made with AIC/BIC, residual checks and out-of-sample accuracy.`;
  const L = S.d.acf_pacf["log AQI (long, 400 lags)"];
  plot("ch-acflong", [{ type: "bar", x: L.lags.slice(1), y: L.acf.slice(1), marker: { color: C.accent() }, hovertemplate: "lag %{x}: %{y:.3f}<extra></extra>" }], { hovermode: "closest", bargap: 0, xaxis: { title: { text: "lag (days)" } }, shapes: [{ type: "line", x0: 365, x1: 365, yref: "paper", y0: 0, y1: 1, line: { color: css("--danger"), dash: "dot", width: 1 } }] });
}

const FAMILY_INFO = [
  ["Naive", "Tomorrow equals today.", "No assumptions. The benchmark any model must beat."],
  ["Seasonal naive (7d)", "Same weekday last week.", "Benchmark for weekly seasonality."],
  ["Holt-Winters ETS", "Exponentially weighted level, damped trend and 7-day season.", "Additive on log scale; no stationarity needed."],
  ["AR(p)", "Today is a weighted sum of the last p days.", "Stationary series (d = 0). Orders guided by PACF cut-off."],
  ["MA(q)", "Today depends on the last q forecast errors.", "Stationary series; short memory. Expected to fit poorly here."],
  ["ARMA(p,q)", "Both AR and MA terms.", "Stationary series (d = 0); a constant captures the mean."],
  ["ARIMA(p,1,q)", "ARMA on day-to-day changes.", "Handles a unit root by differencing (d = 1)."],
  ["SARIMA(p,d,q)(P,D,Q)[7]", "Adds weekly seasonal AR/MA terms at lags 7, 14, …", "Weekly cycle; 365-day SARIMA is impractical."],
  ["SARIMAX + Fourier", "Regression on annual sine/cosine pairs, with ARMA errors.", "Dynamic harmonic regression: annual seasonality on daily data."],
];
function secModels() {
  const ms = models();
  return `<section id="models">
    ${head("08", "Model comparison", "Every model is fitted to the same log AQI data and scored on the same days on the original AQI scale.")}
    <div class="card flush">${table([{ key: 0, label: "Model" }, { key: 1, label: "Idea" }, { key: 2, label: "Assumptions and fit" }], FAMILY_INFO, { wrap: true })}</div>
    <div class="callout"><strong>Protocol.</strong> Orders are chosen on ${S.d.splits.train[0].slice(0, 4)} to 2023 data. Each model then forecasts 1 to 7 days ahead from every day of 2024 (validation), and the lowest mean RMSE picks the final model. Models are re-estimated on data through 2024 and evaluated the same way on 2025, which was never used for any choice. Parameters stay fixed during each evaluation year; only the filter state is updated with each new observation, so no future data leaks in.</div>
    <div class="card flush" style="margin-top:16px">
      <div style="padding:16px 20px" class="card-head"><div><h3>Test set accuracy, 2025</h3><p class="muted">Lower errors are better; interval coverage should sit near 80% and 95%. Hover or focus a term for its meaning.</p>${glossary()}</div>${seg("testh", S.d.horizons.map((h) => [h, `${h} day${h > 1 ? "s" : ""}`]), S.testH)}</div>
      <div id="tbl-test"></div>
    </div>
    <div class="callout" id="txt-dm"></div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>RMSE by horizon</h3></div><div id="ch-rmse" class="chart"></div></div>
      <div class="card flush"><div style="padding:16px 20px" class="card-head"><div><h3>Validation, 2024</h3><p class="muted">Used for model selection</p></div>${seg("valh", S.d.horizons.map((h) => [h, `${h}d`]), S.valH)}</div><div id="tbl-val"></div></div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="controls">${select("tp-model", ms, S.testModel, "Model")}<div class="control"><label>Horizon</label>${seg("tph", S.d.horizons.map((h) => [h, `${h}d`]), S.testH)}</div></div>
      <div class="card-head"><h3>Actual vs predicted, 2025</h3><p class="muted" id="tp-cap"></p></div>
      <div id="ch-tp" class="chart tall"></div>
    </div>
  </section>`;
}
function metricCols(best) {
  const b = (k, d) => (v) => `${v === best[k] ? "<strong>" : ""}${fmt(v, d)}${v === best[k] ? "</strong>" : ""}`;
  return [
    { key: "model", label: "Model", fmt: (v) => `${esc(v)}${v === S.d.selected_model ? ' <span class="chip accent">selected</span>' : ""}` },
    { key: "MAE", label: "MAE", num: true, fmt: b("MAE", 1) }, { key: "RMSE", label: "RMSE", num: true, fmt: b("RMSE", 1) },
    { key: "MAPE", label: "MAPE %", num: true, fmt: b("MAPE", 1) }, { key: "sMAPE", label: "sMAPE %", num: true, fmt: b("sMAPE", 1) },
    { key: "MASE", label: "MASE", num: true, fmt: b("MASE", 2) }, { key: "bias", label: "Bias", num: true, fmt: (v) => fmt(v, 1) },
    { key: "cov80", label: "Cov 80", num: true, fmt: (v) => fmt(v, 0) }, { key: "cov95", label: "Cov 95", num: true, fmt: (v) => fmt(v, 0) },
    { key: "category_acc", label: "Category acc %", num: true, fmt: b("category_acc", 1) },
    { key: "dm", label: "DM p vs naive", num: true, fmt: (v) => v === undefined ? "" : v === null ? "n/a" : `<span class="chip ${v < 0.05 ? "ok" : ""}">${fmtP(v)}</span>` },
  ];
}
function withDM(rows) {
  const dm = S.d.dm_tests || [];
  // One-sided p-value for "model is more accurate than naive" from the two-sided DM result.
  const oneSided = (t) => (!t || t.stat === null) ? null : t.stat < 0 ? t.p_value / 2 : 1 - t.p_value / 2;
  return rows.map((r) => ({ ...r, dm: r.model === "Naive" ? undefined : oneSided(dm.find((x) => x.model === r.model && x.h === r.h)) }));
}
function bestOf(rows) {
  const lo = (k) => Math.min(...rows.map((r) => r[k])), hi = (k) => Math.max(...rows.map((r) => r[k]));
  return { MAE: lo("MAE"), RMSE: lo("RMSE"), MAPE: lo("MAPE"), sMAPE: lo("sMAPE"), MASE: lo("MASE"), category_acc: hi("category_acc") };
}
function drawModels() {
  const rows = withDM(S.d.test_metrics.filter((r) => r.h === S.testH).sort((a, b) => a.RMSE - b.RMSE));
  $("#tbl-test").innerHTML = table(metricCols(bestOf(rows)), rows, { hl: (r) => r.model === S.d.selected_model });
  const nv = rows.find((r) => r.model === "Naive"), top = rows[0];
  const sig = rows.filter((r) => r.dm !== undefined && r.dm !== null && r.dm < 0.05).map((r) => r.model);
  const gain = (1 - top.RMSE / nv.RMSE) * 100;
  $("#txt-dm").innerHTML = `<strong>Is the gain real?</strong> At ${S.testH} day${S.testH > 1 ? "s" : ""} ahead the best model, ${esc(top.model)}, cuts RMSE by ${fmt(gain, 0)}% versus naive (${fmt(top.RMSE, 1)} vs ${fmt(nv.RMSE, 1)}). ` +
    (sig.length ? `The Diebold-Mariano test finds a significant improvement (p < 0.05) for ${sig.length} model${sig.length > 1 ? "s" : ""}: ${sig.map(esc).join(", ")}.`
      : `However, no model beats naive significantly at the 5% level over one test year (smallest p = ${fmtP(Math.min(...rows.filter((r) => r.dm != null).map((r) => r.dm)))}). Day-to-day ${esc(S.d.city)} AQI is dominated by persistence and sudden shocks (likely weather-driven, e.g. sea breeze and rain), so a univariate model's edge over “tomorrow = today” is modest. Exogenous inputs (wind, rainfall) are the natural next step.`);
  const vrows = S.d.validation_metrics.filter((r) => r.h === S.valH).sort((a, b) => a.RMSE - b.RMSE);
  $("#tbl-val").innerHTML = table(metricCols(bestOf(vrows)).filter((c) => ["model", "MAE", "RMSE", "MASE"].includes(c.key)), vrows, { hl: (r) => r.model === S.d.selected_model });
  const ms = [...new Set(S.d.test_metrics.map((r) => r.model))].sort((a, b) => testRow(b, 1).RMSE - testRow(a, 1).RMSE);
  const shades = [css("--hairline-strong"), css("--series-2"), C.accent()];
  plot("ch-rmse", S.d.horizons.map((h, i) => ({ type: "bar", orientation: "h", name: `${h}d`, y: ms, x: ms.map((m) => testRow(m, h).RMSE), marker: { color: shades[i] }, hovertemplate: `%{y}, ${h}d: %{x:.1f}<extra></extra>` })),
    { barmode: "group", hovermode: "closest", margin: { l: 210, r: 16, t: 28, b: 40 }, xaxis: { title: { text: "RMSE (AQI)" } }, bargap: 0.25 });
  drawTestPath();
}
function drawTestPath() {
  const p = S.d.test_paths[S.testModel][String(S.testH)], r = testRow(S.testModel, S.testH);
  $("#tp-cap").textContent = `RMSE ${fmt(r.RMSE, 1)} · MAE ${fmt(r.MAE, 1)} · 95% coverage ${fmt(r.cov95, 0)}%`;
  plot("ch-tp", [
    { x: [...p.date, ...[...p.date].reverse()], y: [...p.hi95, ...[...p.lo95].reverse()], mode: "lines", fill: "toself", fillcolor: C.band(), line: { width: 0 }, name: "95% interval", hoverinfo: "skip" },
    { x: p.date, y: p.actual, name: "Actual", line: { color: C.ink(), width: 1.4 }, hovertemplate: "%{y:.0f}" },
    { x: p.date, y: p.forecast, name: `Forecast (${S.testH}d ahead)`, line: { color: C.accent(), width: 1.6 }, hovertemplate: "%{y:.0f}" },
  ], { yaxis: { title: { text: "AQI" } }, shapes: bandShapes(Math.max(...p.hi95) * 1.05, 0.05) });
}

function secLags() {
  const so = S.d.selected_orders, ap = S.d.acf_pacf["log AQI"];
  const cand = S.d.candidates;
  const rows = ["AR", "MA", "ARMA", "ARIMA", "SARIMA", "SARIMAX-Fourier"].map((f) => {
    const s = so[f], c = cand.find((x) => x.label === s.label);
    const why = {
      AR: `PACF significant at lags ${ap.significant_pacf_lags.filter((l) => l <= 10).join(", ")}; AIC searched p = 1 to 10`,
      MA: "Slowly decaying ACF means a short MA cannot capture persistence; q = 1 to 10 searched",
      ARMA: "AR and MA mix searched over p, q = 1 to 3",
      ARIMA: "Differenced ACF cuts off quickly; p, q = 0 to 3 with d = 1",
      SARIMA: "Best ARMA and ARIMA orders plus weekly seasonal P, D, Q at s = 7",
      "SARIMAX-Fourier": "K annual harmonic pairs (1 to 4) with small ARMA error orders",
    }[f];
    return { family: f, label: s.label, k: c.k_params, aic: c.aic, bic: c.bic, why };
  });
  return `<section id="lags">
    ${head("09", "Lag selection", "Candidate orders come from the ACF/PACF patterns; the final order within each family has the lowest AIC on training data.")}
    <div class="card flush">${table([{ key: "family", label: "Family" }, { key: "label", label: "Selected" }, { key: "k", label: "Params", num: true }, { key: "aic", label: "AIC", num: true, fmt: (v) => fmt(v, 1) }, { key: "bic", label: "BIC", num: true, fmt: (v) => fmt(v, 1) }, { key: "why", label: "Search rationale" }], rows, { wrap: true })}</div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>AR(p): AIC and BIC vs order</h3></div><div id="ch-ar" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>MA(q): AIC and BIC vs order</h3></div><div id="ch-ma" class="chart short"></div></div>
    </div>
    <div class="callout" id="txt-lags"></div>
  </section>`;
}
function drawLags() {
  const cand = S.d.candidates;
  const curve = (fam, idx) => { const c = cand.filter((x) => x.family === fam).sort((a, b) => a.order[idx] - b.order[idx]); return [c.map((x) => x.order[idx]), c.map((x) => x.aic), c.map((x) => x.bic)]; };
  for (const [id, fam, idx, lab] of [["ch-ar", "AR", 0, "p"], ["ch-ma", "MA", 2, "q"]]) {
    const [x, aic, bic] = curve(fam, idx);
    plot(id, [{ x, y: aic, name: "AIC", mode: "lines+markers", line: { color: C.accent() } }, { x, y: bic, name: "BIC", mode: "lines+markers", line: { color: C.ink(), dash: "dot" } }], { xaxis: { title: { text: lab }, dtick: 1 } });
  }
  const ar = cand.filter((x) => x.family === "AR"), aicBest = ar.reduce((a, b) => a.aic < b.aic ? a : b), bicBest = ar.reduce((a, b) => a.bic < b.bic ? a : b);
  $("#txt-lags").innerHTML = `<strong>Fit vs complexity.</strong> AIC picks AR(${aicBest.order[0]}) and BIC picks AR(${bicBest.order[0]}). BIC penalises each extra parameter by ln(n) ≈ ${fmt(Math.log(aicBest.nobs), 1)} instead of 2, so it prefers smaller models. The MA curve keeps falling with q because a finite MA struggles to mimic long persistence, a sign that MA alone is the wrong family for this series.`;
}

function secAIC() {
  const fams = ["All", ...new Set(S.d.candidates.map((c) => c.family))];
  return `<section id="aic">
    ${head("10", "AIC and BIC", `All ${S.d.candidates.length} candidate fits on training data. Lower is better, but values are only comparable between models with the same differencing.`)}
    <div class="controls">${select("aic-fam", fams, S.aicFamily, "Family")}</div>
    <div class="card flush"><div id="tbl-aic" style="max-height:440px;overflow:auto"></div></div>
    <div class="callout"><strong>Comparability.</strong> Differencing (d or D > 0) removes observations and changes what the likelihood measures, so an ARIMA AIC cannot be compared directly with an ARMA AIC. The column <span class="mono">d</span> marks the groups. Across groups, and to guard against overfitting, the final choice uses out-of-sample RMSE (section 08). Lowest AIC is a guide, not a guarantee of the best forecast.</div>
  </section>`;
}
function drawAIC() {
  let rows = S.d.candidates.filter((c) => S.aicFamily === "All" || c.family === S.aicFamily);
  const [k, dir] = S.aicSort;
  rows = [...rows].sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);
  const chosen = new Set(Object.values(S.d.selected_orders).map((s) => s.label));
  $("#tbl-aic").innerHTML = table([
    { key: "family", label: "Family", sort: true }, { key: "label", label: "Model" },
    { key: "d_total", label: "d", num: true, sort: true }, { key: "k_params", label: "Params", num: true, sort: true },
    { key: "loglik", label: "Log-lik", num: true, sort: true, fmt: (v) => fmt(v, 1) },
    { key: "aic", label: "AIC", num: true, sort: true, fmt: (v) => fmt(v, 1) }, { key: "bic", label: "BIC", num: true, sort: true, fmt: (v) => fmt(v, 1) },
  ], rows, { hl: (r) => chosen.has(r.label) });
  $$("#tbl-aic .sort-btn").forEach((th) => th.addEventListener("click", () => {
    const key = th.dataset.sort; S.aicSort = [key, S.aicSort[0] === key ? -S.aicSort[1] : 1]; drawAIC();
  }));
}

function secDiag() {
  const ms = Object.keys(S.d.diagnostics);
  return `<section id="diagnostics">
    ${head("", "Residual diagnostics", "A good model leaves residuals that look like white noise: no autocorrelation, stable variance, mean near zero.")}
    <div class="controls">${select("dg-model", ms, S.diagModel, "Model")}</div>
    <div class="card flush" style="margin-bottom:16px"><div class="stat-row" id="dg-stats"></div></div>
    <div class="card"><div class="card-head"><h3>Residuals over time (log scale, fit through 2024)</h3></div><div id="ch-dgres" class="chart short"></div></div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><div class="card-head"><h3>Residual ACF</h3></div><div id="ch-dgacf" class="chart short"></div></div>
      <div class="card"><div class="card-head"><h3>Residual QQ plot</h3></div><div id="ch-dgqq" class="chart short"></div></div>
    </div>
    <div class="callout" id="txt-dg"></div>
  </section>`;
}
function drawDiag() {
  const g = S.d.diagnostics[S.diagModel], lb = g.ljung_box;
  const pchip = (p) => `<span class="chip ${p < 0.05 ? "bad" : "ok"}">p ${fmtP(p)}</span>`;
  $("#dg-stats").innerHTML = [
    stat("Ljung-Box lag 7", fmt(lb[0].stat, 1), pchip(lb[0].p_value), "lb7"),
    stat("Ljung-Box lag 14", fmt(lb[1].stat, 1), pchip(lb[1].p_value), "lb14"),
    stat("Ljung-Box lag 28", fmt(lb[2].stat, 1), pchip(lb[2].p_value), "lb28"),
    stat("Jarque-Bera", fmt(g.jarque_bera.stat, 0), pchip(g.jarque_bera.p_value), "jb"),
    stat("Mean / std", `${fmt(g.mean, 3)}`, `std ${fmt(g.std, 3)}`, "rmean"),
  ].join("");
  popNumbers($("#dg-stats"));
  plot("ch-dgres", [{ x: g.series.date, y: g.series.value, line: { color: C.accent(), width: 0.8 }, hovertemplate: "%{y:.3f}<extra></extra>" }], { showlegend: false, shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: C.ink(), width: 1 } }] });
  acfBars("ch-dgacf", g.acf.map((_, i) => i), g.acf, g.band, css("--danger"));
  plot("ch-dgqq", [{ x: g.qq.theoretical, y: g.qq.sample, mode: "markers", marker: { size: 4, color: C.accent() }, hoverinfo: "skip" }, { x: [-4, 4], y: [-4, 4], mode: "lines", line: { color: C.ink(), dash: "dot", width: 1 }, hoverinfo: "skip" }], { showlegend: false, hovermode: false, xaxis: { title: { text: "theoretical" } }, yaxis: { title: { text: "sample" } } });
  const white = lb.every((x) => x.p_value >= 0.05), sig = g.acf.slice(1).map((v, i) => [i + 1, v]).filter(([, v]) => Math.abs(v) > g.band).map(([l]) => l);
  $("#txt-dg").innerHTML = `<strong>Reading.</strong> ${white ? "Ljung-Box does not reject white noise at lags 7, 14 or 28: the model has captured the serial dependence." : `Ljung-Box rejects white noise (p ${fmtP(lb[0].p_value)} at lag 7), so some structure remains${sig.length ? `, visible at residual lags ${sig.slice(0, 6).join(", ")}` : ""}. With nearly ${fmt(g.series.value.length, 0)} observations the test is very sensitive, so small, practically harmless correlations also trigger it; compare magnitudes in the ACF.`} Residuals have skew ${fmt(g.jarque_bera.skew, 2)} and excess kurtosis ${fmt(g.jarque_bera.excess_kurtosis, 1)}: heavier tails than normal (pollution spikes), so nominal intervals can under-cover extreme days. Variance in the first vs second half: ${fmt(g.var_first_half, 3)} vs ${fmt(g.var_second_half, 3)}.`;
}

function secLimits() {
  return `<section id="limits" style="border-bottom:0">
    ${head("", "Limitations", "What these models can and cannot tell you.")}
    <div class="grid g2">
      <div class="card"><h3>Data</h3><ul class="clean">
        <li>City AQI is an average of station AQIs; the station network grew over time, so early years are excluded from modelling.</li>
        <li>Bulletin AQI is reported once a day and capped at 500; values are used as published, not recomputed from pollutants.</li>
        <li>Univariate: no weather, wind, festivals (Diwali), or crop-burning inputs, which drive many spikes.</li>
      </ul></div>
      <div class="card"><h3>Method</h3><ul class="clean">
        <li>Linear Gaussian models on log AQI: sudden events are hard to anticipate, and residual tails are heavier than normal.</li>
        <li>Parameters are fixed during each evaluation year; regime changes (policy, lockdowns) are only absorbed after refitting.</li>
        <li>Accuracy was evaluated for 1, 3 and 7 days ahead; longer horizons lean on average seasonal patterns.</li>
      </ul></div>
    </div>
    <p class="disclaimer">Data: CPCB National AQI daily bulletins, compiled by UrbanEmissions.info (GPL-3.0). Built with pandas, statsmodels, FastAPI and Plotly.</p>
  </section>`;
}

/* ---------- motion helpers (transitions.dev; all motion conveys a state change) ---------- */
// Sliding tabs: JS writes the active tab's offset/width onto the pill; CSS owns the tween.
function movePill(bar, animate) {
  const pill = bar.querySelector(".t-tabs-pill"), tab = bar.querySelector('[aria-selected="true"]') || bar.querySelector(".t-tab");
  if (!pill || !tab) return;
  if (!animate) {
    const prev = pill.style.transition;
    pill.style.transition = "none";
    pill.style.transform = `translateX(${tab.offsetLeft}px)`;
    pill.style.width = `${tab.offsetWidth}px`;
    void pill.offsetWidth;
    pill.style.transition = prev;
  } else {
    pill.style.transform = `translateX(${tab.offsetLeft}px)`;
    pill.style.width = `${tab.offsetWidth}px`;
  }
}
function placePills() { $$(".t-tabs").forEach((b) => movePill(b, false)); }

// Number pop-in: only the digits that changed since the previous render re-enter.
function popNumbers(root = document) {
  S.prevNums = S.prevNums || {};
  $$(".t-digit-group[data-key]", root).forEach((g) => {
    const str = g.textContent.trim(), prev = S.prevNums[g.dataset.key] ?? "";
    S.prevNums[g.dataset.key] = str;
    if (prev === str) return;
    let same = 0;
    while (same < prev.length && same < str.length && prev[same] === str[same]) same++;
    g.classList.remove("is-animating");
    g.replaceChildren();
    const chars = [...str];
    chars.forEach((ch, i) => {
      const span = document.createElement("span");
      span.className = "t-digit";
      span.textContent = ch;
      if (i < same) span.dataset.same = "";
      if (i === chars.length - 2) span.dataset.stagger = "1";
      else if (i === chars.length - 1) span.dataset.stagger = "2";
      g.appendChild(span);
    });
    void g.offsetHeight;
    g.classList.add("is-animating");
  });
}

// Tooltip glossary: one bubble shared by every term, travelling between triggers.
const TERMS = [
  ["MAE", "Mean absolute error, in AQI points"],
  ["RMSE", "Root mean squared error: punishes big misses more"],
  ["MAPE / sMAPE", "Average percentage error (sMAPE is the symmetric form)"],
  ["MASE", "MAE divided by the naive model's training MAE; below 1 beats naive"],
  ["Coverage", "Share of real days inside the 80% and 95% bands"],
  ["Category acc", "Days where the predicted CPCB AQI band was correct"],
  ["DM p", "Diebold-Mariano test: p < 0.05 means significantly better than naive"],
];
function glossary() {
  return `<div class="t-tt-group glossary" id="glossary">${TERMS.map(([t, d]) => `<button type="button" class="t-tt-trigger" data-tooltip="${esc(d)}" aria-describedby="tt-gloss">${t}</button>`).join("")}<span class="t-tt" id="tt-gloss" role="tooltip" aria-hidden="true" data-show="false"><span class="t-tt-text"></span></span></div>`;
}
function bindGlossary() {
  const group = $("#glossary");
  if (!group) return;
  const tip = group.querySelector(".t-tt"), text = tip.querySelector(".t-tt-text");
  const hide = () => { tip.setAttribute("data-show", "false"); tip.setAttribute("aria-hidden", "true"); };
  const place = (trigger) => {
    const showing = tip.getAttribute("data-show") === "true";
    text.textContent = trigger.getAttribute("data-tooltip") || "";
    const cs = getComputedStyle(tip);
    const width = Math.ceil(text.scrollWidth + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight));
    const g = group.getBoundingClientRect(), r = trigger.getBoundingClientRect();
    let x = r.left - g.left + r.width / 2 - width / 2;
    // keep the bubble inside the viewport (the glossary wraps on narrow screens)
    x = Math.max(8 - g.left, Math.min(x, document.documentElement.clientWidth - g.left - width - 8));
    tip.style.bottom = `${g.bottom - r.top + 8}px`;
    if (!showing) {
      tip.style.transition = "none";
      tip.style.width = `${width}px`;
      tip.style.setProperty("--tt-x", `${x}px`);
      void tip.offsetWidth;
      tip.style.transition = "";
    } else {
      tip.style.width = `${width}px`;
      tip.style.setProperty("--tt-x", `${x}px`);
    }
    tip.setAttribute("data-show", "true");
    tip.setAttribute("aria-hidden", "false");
  };
  $$(".t-tt-trigger", group).forEach((t) => {
    t.addEventListener("pointerenter", () => place(t));
    t.addEventListener("focus", () => place(t));
    t.addEventListener("blur", hide);
  });
  group.addEventListener("pointerleave", hide);
  group.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
}

// Toast: slower in than out; one class gives the asymmetry.
let toastTimer;
function toast(msg) {
  const el = $("#toast");
  $("#toast-text").textContent = msg;
  el.classList.add("is-open");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-open"), 2800);
}

// Icon swap: moon while light (click for dark), sun while dark.
function setThemeIcon() {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  $("#theme-icon").dataset.state = dark ? "b" : "a";
  $("#theme").setAttribute("aria-pressed", String(dark));
}

/* ---------- wiring ---------- */
function selectTab(bar, v, animate = true) {
  $$(".t-tab", bar).forEach((x) => x.setAttribute("aria-selected", String(x.dataset.v === String(v))));
  movePill(bar, animate);
}
function bindSeg(name, fn) {
  $$(`[data-seg="${name}"]`).forEach((bar) => {
    const tabs = $$(".t-tab", bar);
    tabs.forEach((b) => b.addEventListener("click", () => { selectTab(bar, b.dataset.v); fn(b.dataset.v); }));
    bar.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      const i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus(); next.click(); e.preventDefault();
    });
  });
}
function syncSeg(name, v) { $$(`[data-seg="${name}"]`).forEach((bar) => selectTab(bar, v)); }

function drawAll() {
  drawForecast(); drawData(); drawEDA(); drawMissing(); drawStationarity(); drawTransform();
  drawDecomp(); drawACF(); drawModels(); drawLags(); drawAIC(); drawDiag();
}

function render() {
  const d = S.d;
  S.fcModel = d.selected_model; S.testModel = d.selected_model;
  S.diagModel = d.diagnostics[d.selected_model] ? d.selected_model : Object.keys(d.diagnostics)[0];
  $("#content").innerHTML = [secForecast(), secData(), secEDA(), secMissing(), secStationarity(), secTransform(), secDecomp(), secACF(), secModels(), secLags(), secAIC(), secDiag(), secLimits()].join("");
  $("#loading").hidden = true; $("#content").hidden = false;

  $("#fc-model").addEventListener("change", (e) => { S.fcModel = e.target.value; drawForecast(); });
  let t;
  $("#fc-h").addEventListener("input", (e) => { S.fcH = +e.target.value; $("#fc-h-out").textContent = `${S.fcH} day${S.fcH > 1 ? "s" : ""}`; clearTimeout(t); t = setTimeout(drawForecast, 150); });
  bindSeg("hist", (v) => drawEDA(v));
  bindSeg("acf", (v) => { S.acfKey = v; drawACF(); });
  bindSeg("testh", (v) => { S.testH = +v; syncSeg("tph", v); drawModels(); });
  bindSeg("tph", (v) => { S.testH = +v; syncSeg("testh", v); drawModels(); });
  bindSeg("valh", (v) => { S.valH = +v; drawModels(); });
  $("#tp-model").addEventListener("change", (e) => { S.testModel = e.target.value; drawTestPath(); });
  $("#aic-fam").addEventListener("change", (e) => { S.aicFamily = e.target.value; drawAIC(); });
  $("#dg-model").addEventListener("change", (e) => { S.diagModel = e.target.value; drawDiag(); });
  drawAll();
  placePills();
  popNumbers($("#forecast"));
  bindGlossary();
  $("#fc-csv").addEventListener("click", () => toast(`Downloading ${S.fcH}-day ${S.city} forecast · ${S.fcModel}`));
  observeNav();
}

function observeNav() {
  const links = $$(".sidenav a, .mobnav a");
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => { if (en.isIntersecting) { links.forEach((a) => { const on = a.getAttribute("href") === `#${en.target.id}`; a.classList.toggle("active", on); if (on && a.parentElement.classList.contains("mobnav")) { const n = a.parentElement; n.scrollTo({ left: a.offsetLeft - (n.clientWidth - a.offsetWidth) / 2, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); } }); } });
  }, { rootMargin: "-30% 0px -65% 0px" });
  $$("main section").forEach((s) => io.observe(s));
}

async function loadCity(city) {
  S.city = city;
  $("#loading").hidden = false; $("#content").hidden = true;
  try {
    const r = await fetch(`/api/city/${encodeURIComponent(city)}`);
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    S.d = await r.json();
    document.title = `${city} AQI Forecasting Lab`;
    render();
  } catch (e) {
    $("#loading").innerHTML = `<div class="error-box">Could not load ${esc(city)}: ${esc(e.message)}. Check that the server is running and that <span class="mono">python run_pipeline.py ${esc(city)}</span> has completed.</div>`;
  }
}

async function init() {
  const r = await fetch("/api/cities").then((x) => x.json());
  S.bands = r.bands;
  const sel = $("#city");
  sel.innerHTML = r.cities.map((c) => `<option>${esc(c)}</option>`).join("");
  sel.addEventListener("change", () => loadCity(sel.value));
  $("#theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setThemeIcon();
    try { localStorage.setItem("theme", next); } catch (e) {}
    if (S.d) drawAll();
  });
  setThemeIcon();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { setThemeIcon(); if (S.d && !document.documentElement.dataset.theme) drawAll(); });
  let rz;
  addEventListener("resize", () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(placePills); });
  if (!r.cities.length) { $("#loading").innerHTML = `<div class="error-box">No trained cities found. Run <span class="mono">python run_pipeline.py</span> first.</div>`; return; }
  loadCity(r.cities.includes("Mumbai") ? "Mumbai" : r.cities[0]);
}
init();
