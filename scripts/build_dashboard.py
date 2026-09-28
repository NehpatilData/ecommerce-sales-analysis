"""
build_dashboard.py
==================
Generate ONE self-contained interactive HTML dashboard from the star schema.

Inputs (read-only):
    Data/clean/fact_orders.csv
    Data/clean/dim_product.csv
    Data/clean/dim_region.csv

Output:
    dashboard/index.html

The page is fully self-contained: the data is embedded as JSON and every chart is
drawn with hand-written SVG + vanilla JavaScript. There is no CDN, no build step
and no server - it opens straight from disk, including offline.

It shows:
  * KPI cards: revenue, profit, orders, customers, profit margin
  * monthly sales trend (revenue + profit)
  * revenue by category
  * profit by region
  * top products by revenue
with interactive filters for year, region and category.

Usage
-----
    python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = PROJECT_ROOT / "Data" / "clean"
FACT_ORDERS = CLEAN_DIR / "fact_orders.csv"
DIM_PRODUCT = CLEAN_DIR / "dim_product.csv"
DIM_REGION = CLEAN_DIR / "dim_region.csv"
OUT_DIR = PROJECT_ROOT / "dashboard"
OUT_FILE = OUT_DIR / "index.html"

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
PAYLOAD_MARKER = "__DASHBOARD_PAYLOAD__"
TOP_N = 10


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def log(message: str = "") -> None:
    print(message, flush=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --------------------------------------------------------------------------- #
# Payload - a compact, filter-friendly extract of the star schema
# --------------------------------------------------------------------------- #
def build_payload() -> dict:
    """Flatten the fact table plus the attributes the dashboard needs.

    Row layout (positional, to keep the JSON small):
        [year, month, regionIdx, productIdx, customerIdx, revenue, profit]
    year = -1 and month = 0 for the rows whose order_date is blank.
    """
    fact = read_csv(FACT_ORDERS)
    dim_product = read_csv(DIM_PRODUCT)
    dim_region = read_csv(DIM_REGION)

    # --- dimensions ------------------------------------------------------- #
    products_df = (
        dim_product[["product_id", "product_name", "category"]]
        .drop_duplicates(subset=["product_id"])
        .sort_values("product_id")
    )
    categories = sorted(products_df["category"].unique().tolist())
    category_index = {name: i for i, name in enumerate(categories)}
    product_index = {pid: i for i, pid in enumerate(products_df["product_id"])}
    products = [
        {"id": row.product_id, "name": row.product_name, "cat": category_index[row.category]}
        for row in products_df.itertuples(index=False)
    ]

    regions = sorted(dim_region["region"].unique().tolist())
    region_index = {name: i for i, name in enumerate(regions)}
    region_name_of_id = dict(zip(dim_region["region_id"], dim_region["region"]))

    customers = sorted(fact["customer_id"].unique().tolist())
    customer_index = {cid: i for i, cid in enumerate(customers)}

    # --- calendar --------------------------------------------------------- #
    parsed = pd.to_datetime(fact["order_date"], format=DATE_FORMAT, errors="coerce")
    years = sorted(int(y) for y in parsed.dt.year.dropna().unique().tolist())

    revenue = pd.to_numeric(fact["sales_amount"], errors="coerce")
    profit = pd.to_numeric(fact["profit"], errors="coerce")

    frame = pd.DataFrame(
        {
            "year": parsed.dt.year.fillna(-1).astype(int),
            "month": parsed.dt.month.fillna(0).astype(int),
            "region": fact["region_id"].map(region_name_of_id).map(region_index),
            "product": fact["product_id"].map(product_index),
            "customer": fact["customer_id"].map(customer_index),
            "revenue": revenue,
            "profit": profit,
        }
    )

    rows = [
        [int(a), int(b), int(c), int(d), int(e), round(float(f), 2), round(float(g), 2)]
        for a, b, c, d, e, f, g in zip(
            frame["year"], frame["month"], frame["region"], frame["product"],
            frame["customer"], frame["revenue"], frame["profit"],
        )
    ]

    undated = int((frame["year"] == -1).sum())
    dated = len(rows) - undated

    return {
        "categories": categories,
        "regions": regions,
        "years": years,
        "products": products,
        "rows": rows,
        "topN": TOP_N,
        "meta": {
            "factRows": len(rows),
            "datedRows": dated,
            "undatedRows": undated,
            "productCount": len(products),
            "customerCount": len(customers),
            "dateMin": None if not years else f"{min(years)}-01-01",
            "dateMax": None if not years else f"{max(years)}-12-31",
            "source": "Data/clean/fact_orders.csv + dim_product.csv + dim_region.csv",
        },
    }


# --------------------------------------------------------------------------- #
# HTML - head and stylesheet (plain strings: the JSON is injected afterwards)
# --------------------------------------------------------------------------- #
HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E-Commerce Sales Dashboard</title>
<style>
  :root{
    --bg:#eef2f9; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --accent:#2563eb; --accent-soft:#dbeafe; --profit:#10b981; --profit-soft:#d1fae5;
    --warn:#f59e0b; --shadow:0 1px 2px rgba(15,23,42,.06), 0 8px 24px rgba(15,23,42,.06);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--bg); color:var(--ink); font-size:14px;
    font-family:"Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1280px; margin:0 auto; padding:22px 20px 40px}

  header.top{
    background:var(--card); border:1px solid var(--line); border-radius:14px;
    box-shadow:var(--shadow); padding:18px 20px; margin-bottom:18px;
  }
  .title-row{display:flex; flex-wrap:wrap; gap:14px; align-items:baseline; justify-content:space-between}
  h1{margin:0; font-size:20px; letter-spacing:-.01em}
  h1 span{color:var(--muted); font-weight:500}
  .sub{color:var(--muted); font-size:12.5px; margin-top:5px}

  .filters{
    display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;
    margin-top:16px; padding-top:16px; border-top:1px solid var(--line);
  }
  .field{display:flex; flex-direction:column; gap:5px; min-width:150px}
  .field label{font-size:11px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--muted)}
  select{
    appearance:none; background:#fff; border:1px solid var(--line); border-radius:9px;
    padding:8px 30px 8px 11px; font:inherit; font-size:13px; color:var(--ink); cursor:pointer;
    background-image:url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2364748b' d='M2 4l4 4 4-4z'/%3E%3C/svg%3E");
    background-repeat:no-repeat; background-position:right 10px center;
  }
  select:focus{outline:2px solid var(--accent-soft); border-color:var(--accent)}
  button.reset{
    border:1px solid var(--line); background:#fff; color:var(--muted); border-radius:9px;
    padding:8px 14px; font:inherit; font-size:13px; font-weight:600; cursor:pointer;
  }
  button.reset:hover{background:#f8fafc; color:var(--ink)}
  .chip{
    margin-left:auto; font-size:12px; color:var(--muted); background:#f8fafc;
    border:1px solid var(--line); border-radius:999px; padding:6px 12px;
  }
  .chip b{color:var(--ink)}

  .kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(176px,1fr)); gap:14px; margin-bottom:18px}
  .kpi{
    background:var(--card); border:1px solid var(--line); border-radius:14px;
    box-shadow:var(--shadow); padding:15px 16px;
  }
  .kpi .k-label{font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:var(--muted)}
  .kpi .k-value{font-size:23px; font-weight:700; margin-top:7px; letter-spacing:-.02em; font-variant-numeric:tabular-nums}
  .kpi .k-foot{font-size:11.5px; color:var(--muted); margin-top:5px}
  .kpi.accent .k-value{color:var(--accent)}
  .kpi.profit .k-value{color:var(--profit)}

  .grid{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px}
  .card{
    background:var(--card); border:1px solid var(--line); border-radius:14px;
    box-shadow:var(--shadow); padding:16px 18px 14px;
  }
  .card.span2{grid-column:1 / -1}
  .card h2{margin:0 0 2px; font-size:14.5px}
  .card .note{color:var(--muted); font-size:12px; margin-bottom:12px}
  .legend{display:flex; gap:16px; flex-wrap:wrap; margin:2px 0 12px; font-size:12px; color:var(--muted)}
  .legend i{display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px}
  svg{display:block; width:100%; height:auto; overflow:visible}
  .bar-row{cursor:default}
  .bar-row:hover rect.track{fill:#eef2f7}
  .empty{color:var(--muted); font-size:13px; padding:24px 0; text-align:center}

  #tip{
    position:fixed; z-index:99; pointer-events:none; opacity:0; transition:opacity .1s;
    background:#0f172a; color:#f8fafc; border-radius:9px; padding:9px 11px; font-size:12px;
    box-shadow:0 8px 24px rgba(15,23,42,.25); max-width:280px; line-height:1.5;
  }
  #tip .t-title{font-weight:700; margin-bottom:4px}
  #tip .t-row{display:flex; justify-content:space-between; gap:14px}
  #tip .t-row span:last-child{font-variant-numeric:tabular-nums; font-weight:600}

  footer{margin-top:22px; color:var(--muted); font-size:11.5px; line-height:1.7}
  footer code{background:#e8edf6; border-radius:5px; padding:1px 5px; font-size:11px}
  @media (max-width:880px){ .grid{grid-template-columns:1fr} }
</style>
</head>
"""

HTML_BODY = """<body>
<div class="wrap">
  <header class="top">
    <div class="title-row">
      <div>
        <h1>E-Commerce Sales Dashboard</h1>
        <div class="sub">Star schema: fact_orders joined to dim_product and dim_region &middot; generated from Data/clean/</div>
      </div>
      <div class="chip" id="scopeChip">loading&hellip;</div>
    </div>

    <div class="filters">
      <div class="field">
        <label for="fYear">Year</label>
        <select id="fYear"></select>
      </div>
      <div class="field">
        <label for="fRegion">Region</label>
        <select id="fRegion"></select>
      </div>
      <div class="field">
        <label for="fCategory">Category</label>
        <select id="fCategory"></select>
      </div>
      <button class="reset" id="btnReset" type="button">Reset filters</button>
    </div>
  </header>

  <section class="kpis" id="kpis"></section>

  <section class="grid">
    <div class="card span2">
      <h2>Monthly sales trend</h2>
      <div class="note" id="trendNote"></div>
      <div class="legend">
        <span><i style="background:#2563eb"></i>Revenue</span>
        <span><i style="background:#10b981"></i>Profit</span>
        <span>hover a point for detail</span>
      </div>
      <div id="trendChart"></div>
    </div>

    <div class="card">
      <h2>Revenue by category</h2>
      <div class="note">Total sales_amount per product category</div>
      <div id="catChart"></div>
    </div>

    <div class="card">
      <h2>Profit by region</h2>
      <div class="note">Total profit per region</div>
      <div id="regionChart"></div>
    </div>

    <div class="card span2">
      <h2>Top products by revenue</h2>
      <div class="note" id="prodNote"></div>
      <div id="prodChart"></div>
    </div>
  </section>

  <footer id="foot"></footer>
</div>
<div id="tip"></div>
"""

HTML_PAYLOAD = """<script id="payload" type="application/json">__DASHBOARD_PAYLOAD__</script>
"""

APP_JS = """<script>
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("payload").textContent);
  var CATEGORIES = DATA.categories;
  var REGIONS = DATA.regions;
  var PRODUCTS = DATA.products;
  var YEARS = DATA.years;
  var ROWS = DATA.rows;
  var META = DATA.meta;
  var TOP_N = DATA.topN;

  var state = { year: "all", region: "all", category: "all" };

  /* ------------------------------ formatting ---------------------------- */
  var nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function money(v){ return nf0.format(Math.round(v)); }
  function compact(v){
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return nf0.format(v);
  }
  function pctOf(profit, revenue){ return (revenue ? (profit / revenue) * 100 : 0).toFixed(2) + "%"; }

  /* ------------------------------- filtering ---------------------------- */
  function matches(r){
    if (state.year !== "all" && String(r[0]) !== state.year) return false;
    if (state.region !== "all" && String(r[2]) !== state.region) return false;
    if (state.category !== "all" && String(PRODUCTS[r[3]].cat) !== state.category) return false;
    return true;
  }
  function currentRows(){ return ROWS.filter(matches); }

  function totals(rs){
    var revenue = 0, profit = 0, cust = new Set(), i, r;
    for (i = 0; i < rs.length; i++){
      r = rs[i];
      revenue += r[5]; profit += r[6]; cust.add(r[4]);
    }
    return { revenue: revenue, profit: profit, orders: rs.length, customers: cust.size };
  }

  function trendSeries(rs){
    var map = new Map(), i, r, k, d;
    for (i = 0; i < rs.length; i++){
      r = rs[i];
      if (r[1] === 0) continue;                 /* undated rows have no place on a monthly axis */
      k = r[0] * 100 + r[1];
      d = map.get(k);
      if (!d){ d = { key: k, year: r[0], month: r[1], revenue: 0, profit: 0, orders: 0 }; map.set(k, d); }
      d.revenue += r[5]; d.profit += r[6]; d.orders += 1;
    }
    return Array.from(map.values()).sort(function (a, b){ return a.key - b.key; });
  }

  function byCategory(rs){
    var out = CATEGORIES.map(function (name, i){ return { name: name, idx: i, revenue: 0, profit: 0, orders: 0 }; });
    var i, r;
    for (i = 0; i < rs.length; i++){
      r = rs[i];
      out[PRODUCTS[r[3]].cat].revenue += r[5];
      out[PRODUCTS[r[3]].cat].profit += r[6];
      out[PRODUCTS[r[3]].cat].orders += 1;
    }
    return out.filter(function (c){ return c.orders > 0; }).sort(function (a, b){ return b.revenue - a.revenue; });
  }

  function byRegion(rs){
    var out = REGIONS.map(function (name, i){ return { name: name, idx: i, revenue: 0, profit: 0, orders: 0 }; });
    var i, r;
    for (i = 0; i < rs.length; i++){
      r = rs[i];
      out[r[2]].revenue += r[5];
      out[r[2]].profit += r[6];
      out[r[2]].orders += 1;
    }
    return out.filter(function (g){ return g.orders > 0; }).sort(function (a, b){ return b.profit - a.profit; });
  }

  function topProducts(rs){
    var map = new Map(), i, r, p;
    for (i = 0; i < rs.length; i++){
      r = rs[i];
      p = map.get(r[3]);
      if (!p){ p = { idx: r[3], revenue: 0, profit: 0, orders: 0 }; map.set(r[3], p); }
      p.revenue += r[5]; p.profit += r[6]; p.orders += 1;
    }
    return Array.from(map.values())
      .sort(function (a, b){ return b.revenue - a.revenue; })
      .slice(0, TOP_N);
  }

  /* -------------------------------- tooltip ----------------------------- */
  var tip = document.getElementById("tip");
  function moveTip(evt){
    var pad = 14;
    var x = evt.clientX + pad, y = evt.clientY + pad;
    var box = tip.getBoundingClientRect();
    if (x + box.width > window.innerWidth - 8) x = evt.clientX - box.width - pad;
    if (y + box.height > window.innerHeight - 8) y = evt.clientY - box.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function showTip(evt, title, pairs){
    var html = '<div class="t-title">' + title + "</div>", i;
    for (i = 0; i < pairs.length; i++){
      html += '<div class="t-row"><span>' + pairs[i][0] + "</span><span>" + pairs[i][1] + "</span></div>";
    }
    tip.innerHTML = html;
    tip.style.opacity = 1;
    moveTip(evt);
  }
  function hideTip(){ tip.style.opacity = 0; }

  /* ------------------------------- svg utils ---------------------------- */
  var SVG_NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, text){
    var n = document.createElementNS(SVG_NS, tag), k;
    if (attrs){ for (k in attrs){ n.setAttribute(k, attrs[k]); } }
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* ------------------------------- line chart --------------------------- */
  function drawTrend(series){
    var host = document.getElementById("trendChart");
    host.innerHTML = "";
    if (!series.length){
      host.innerHTML = '<div class="empty">No dated rows for this selection.</div>';
      return;
    }
    var W = 980, H = 320, mt = 16, mr = 18, mb = 40, ml = 66;
    var iw = W - ml - mr, ih = H - mt - mb;
    var maxRev = 0, i;
    for (i = 0; i < series.length; i++){ if (series[i].revenue > maxRev) maxRev = series[i].revenue; }
    var yMax = (maxRev > 0 ? maxRev : 1) * 1.12;
    var n = series.length;
    function xAt(j){ return n === 1 ? ml + iw / 2 : ml + (j * iw) / (n - 1); }
    function yAt(v){ return mt + ih - (v / yMax) * ih; }

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Monthly revenue and profit" });

    var ticks = 5, t, v, yy;
    for (t = 0; t <= ticks; t++){
      v = (yMax / ticks) * t;
      yy = yAt(v);
      svg.appendChild(el("line", { x1: ml, x2: W - mr, y1: yy, y2: yy, stroke: "#eef2f7", "stroke-width": 1 }));
      svg.appendChild(el("text", { x: ml - 10, y: yy + 4, "text-anchor": "end", fill: "#94a3b8", "font-size": 11 }, compact(v)));
    }

    var every = n > 14 ? 2 : 1;
    for (i = 0; i < n; i++){
      if (i % every !== 0 && i !== n - 1) continue;
      svg.appendChild(el("text", { x: xAt(i), y: H - 14, "text-anchor": "middle", fill: "#94a3b8", "font-size": 11 },
        MONTHS[series[i].month - 1] + " " + String(series[i].year).slice(2)));
    }

    var area = "M" + xAt(0) + " " + yAt(0);
    for (i = 0; i < n; i++){ area += " L" + xAt(i) + " " + yAt(series[i].revenue); }
    area += " L" + xAt(n - 1) + " " + yAt(0) + " Z";
    svg.appendChild(el("path", { d: area, fill: "#2563eb", "fill-opacity": 0.1 }));

    var line = "";
    for (i = 0; i < n; i++){ line += (i ? " L" : "M") + xAt(i) + " " + yAt(series[i].revenue); }
    svg.appendChild(el("path", { d: line, fill: "none", stroke: "#2563eb", "stroke-width": 2.4, "stroke-linejoin": "round" }));

    var pline = "";
    for (i = 0; i < n; i++){ pline += (i ? " L" : "M") + xAt(i) + " " + yAt(series[i].profit); }
    svg.appendChild(el("path", { d: pline, fill: "none", stroke: "#10b981", "stroke-width": 2.2, "stroke-dasharray": "5 4", "stroke-linejoin": "round" }));

    var bandW = n > 1 ? iw / (n - 1) : iw;
    for (i = 0; i < n; i++){
      (function (idx){
        var d = series[idx], cx = xAt(idx);
        var g = el("g");
        var guide = el("line", { x1: cx, x2: cx, y1: mt, y2: mt + ih, stroke: "#cbd5e1", "stroke-width": 1, opacity: 0 });
        var c1 = el("circle", { cx: cx, cy: yAt(d.revenue), r: 4.5, fill: "#fff", stroke: "#2563eb", "stroke-width": 2.4, opacity: 0 });
        var c2 = el("circle", { cx: cx, cy: yAt(d.profit), r: 4, fill: "#fff", stroke: "#10b981", "stroke-width": 2.2, opacity: 0 });
        g.appendChild(guide); g.appendChild(c1); g.appendChild(c2);
        var hit = el("rect", { x: cx - bandW / 2, y: mt, width: bandW, height: ih, fill: "transparent" });
        hit.style.cursor = "crosshair";
        hit.addEventListener("mouseenter", function (e){
          guide.setAttribute("opacity", 1);
          c1.setAttribute("opacity", 1);
          c2.setAttribute("opacity", 1);
          showTip(e, MONTHS[d.month - 1] + " " + d.year, [
            ["Revenue", money(d.revenue)],
            ["Profit", money(d.profit)],
            ["Margin", pctOf(d.profit, d.revenue)],
            ["Orders", nf0.format(d.orders)]
          ]);
        });
        hit.addEventListener("mousemove", moveTip);
        hit.addEventListener("mouseleave", function (){
          guide.setAttribute("opacity", 0);
          c1.setAttribute("opacity", 0);
          c2.setAttribute("opacity", 0);
          hideTip();
        });
        g.appendChild(hit);
        svg.appendChild(g);
      })(i);
    }
    host.appendChild(svg);
  }

  /* -------------------------------- bar chart --------------------------- */
  function drawBars(hostId, items, opts){
    var host = document.getElementById(hostId);
    host.innerHTML = "";
    if (!items.length){
      host.innerHTML = '<div class="empty">No data for this selection.</div>';
      return;
    }
    var W = 980, rowH = 30, barH = 15;
    var leftW = opts.leftW, rightW = 92;
    var H = items.length * rowH + 10;
    var iw = W - leftW - rightW;
    var max = 0, i, v;
    for (i = 0; i < items.length; i++){ v = opts.value(items[i]); if (v > max) max = v; }
    if (max <= 0) max = 1;

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": opts.label });
    for (i = 0; i < items.length; i++){
      (function (idx){
        var it = items[idx];
        var yTop = idx * rowH + 6, cy = yTop + barH / 2;
        var w = Math.max(2, (opts.value(it) / max) * iw);
        var g = el("g", { "class": "bar-row" });
        g.appendChild(el("rect", { "class": "track", x: leftW, y: yTop, width: iw, height: barH, rx: 4, fill: "#f6f8fc" }));
        g.appendChild(el("rect", { x: leftW, y: yTop, width: w, height: barH, rx: 4, fill: opts.color }));
        g.appendChild(el("text", { x: leftW - 12, y: cy + 4.5, "text-anchor": "end", fill: "#334155", "font-size": 12.5 }, opts.name(it)));
        g.appendChild(el("text", { x: leftW + w + 10, y: cy + 4.5, fill: "#0f172a", "font-size": 12.5, "font-weight": 600 }, compact(opts.value(it))));
        g.addEventListener("mouseenter", function (e){ showTip(e, opts.name(it), opts.tip(it)); });
        g.addEventListener("mousemove", moveTip);
        g.addEventListener("mouseleave", hideTip);
        svg.appendChild(g);
      })(i);
    }
    host.appendChild(svg);
  }

  /* ---------------------------------- KPIs ------------------------------ */
  function renderKpis(t){
    var host = document.getElementById("kpis");
    var cards = [
      { cls: "accent", label: "Revenue", value: money(t.revenue), foot: "SUM(sales_amount)" },
      { cls: "profit", label: "Profit", value: money(t.profit), foot: "SUM(profit)" },
      { cls: "", label: "Profit margin", value: pctOf(t.profit, t.revenue), foot: "profit / revenue" },
      { cls: "", label: "Orders", value: nf0.format(t.orders), foot: "order lines in scope" },
      { cls: "", label: "Customers", value: nf0.format(t.customers), foot: "distinct customer_id" }
    ];
    var html = "", i, c;
    for (i = 0; i < cards.length; i++){
      c = cards[i];
      html += '<div class="kpi ' + c.cls + '"><div class="k-label">' + c.label + "</div>" +
              '<div class="k-value">' + c.value + "</div>" +
              '<div class="k-foot">' + c.foot + "</div></div>";
    }
    host.innerHTML = html;
  }

  /* --------------------------------- render ----------------------------- */
  function render(){
    var rs = currentRows();
    var t = totals(rs);

    renderKpis(t);

    var trend = trendSeries(rs);
    drawTrend(trend);
    document.getElementById("trendNote").textContent =
      trend.length + " month" + (trend.length === 1 ? "" : "s") + " with dated orders" +
      (META.undatedRows > 0
        ? " - " + META.undatedRows + " order lines have a blank order_date and cannot appear here"
        : "");

    drawBars("catChart", byCategory(rs), {
      label: "Revenue by category", color: "#2563eb", leftW: 150,
      name: function (d){ return d.name; },
      value: function (d){ return d.revenue; },
      tip: function (d){
        return [["Revenue", money(d.revenue)], ["Profit", money(d.profit)],
                ["Margin", pctOf(d.profit, d.revenue)], ["Orders", nf0.format(d.orders)]];
      }
    });

    drawBars("regionChart", byRegion(rs), {
      label: "Profit by region", color: "#10b981", leftW: 110,
      name: function (d){ return d.name; },
      value: function (d){ return d.profit; },
      tip: function (d){
        return [["Profit", money(d.profit)], ["Revenue", money(d.revenue)],
                ["Margin", pctOf(d.profit, d.revenue)], ["Orders", nf0.format(d.orders)]];
      }
    });

    var top = topProducts(rs);
    drawBars("prodChart", top, {
      label: "Top products by revenue", color: "#2563eb", leftW: 250,
      name: function (d){ return PRODUCTS[d.idx].name; },
      value: function (d){ return d.revenue; },
      tip: function (d){
        return [["Revenue", money(d.revenue)], ["Profit", money(d.profit)],
                ["Margin", pctOf(d.profit, d.revenue)], ["Orders", nf0.format(d.orders)],
                ["Category", CATEGORIES[PRODUCTS[d.idx].cat]]];
      }
    });
    document.getElementById("prodNote").textContent =
      "Top " + top.length + " of " + META.productCount + " products by revenue in the current selection";

    var scope = [
      state.year === "all" ? "All years" : "Year " + state.year,
      state.region === "all" ? "All regions" : REGIONS[Number(state.region)],
      state.category === "all" ? "All categories" : CATEGORIES[Number(state.category)]
    ];
    document.getElementById("scopeChip").innerHTML =
      "Showing <b>" + nf0.format(rs.length) + "</b> of <b>" + nf0.format(ROWS.length) +
      "</b> order lines &middot; " + scope.join(" &middot; ");
  }

  /* ----------------------------- filter wiring -------------------------- */
  function fillSelect(id, values, labels){
    var html = '<option value="all">All</option>', i;
    for (i = 0; i < values.length; i++){
      html += '<option value="' + values[i] + '">' + labels[i] + "</option>";
    }
    document.getElementById(id).innerHTML = html;
  }

  var yearSel = document.getElementById("fYear");
  var regionSel = document.getElementById("fRegion");
  var catSel = document.getElementById("fCategory");

  yearSel.addEventListener("change", function (){ state.year = yearSel.value; render(); });
  regionSel.addEventListener("change", function (){ state.region = regionSel.value; render(); });
  catSel.addEventListener("change", function (){ state.category = catSel.value; render(); });
  document.getElementById("btnReset").addEventListener("click", function (){
    state.year = "all"; state.region = "all"; state.category = "all";
    yearSel.value = "all"; regionSel.value = "all"; catSel.value = "all";
    render();
  });
  window.addEventListener("scroll", hideTip);

  /* ---------------------------------- boot ------------------------------ */
  fillSelect("fYear", YEARS.map(String), YEARS.map(String));
  fillSelect("fRegion", REGIONS.map(function (_, i){ return String(i); }), REGIONS);
  fillSelect("fCategory", CATEGORIES.map(function (_, i){ return String(i); }), CATEGORIES);

  document.getElementById("foot").innerHTML =
    "Source: <code>" + META.source + "</code><br>" +
    "Scope: " + nf0.format(META.factRows) + " order lines &middot; " + META.productCount + " products &middot; " +
    META.customerCount + " customers &middot; " + REGIONS.length + " regions &middot; " + YEARS.length + " years.<br>" +
    "Monetary values are shown exactly as recorded in the source data; the source does not specify a currency." +
    (META.undatedRows > 0
      ? "<br>Note: " + META.undatedRows + " order lines have a blank order_date (flagged <code>is_invalid_date = Y</code>). " +
        "They are counted in revenue, profit, orders, customers, category, region and product figures while Year = All, " +
        "they never appear in the monthly trend, and they drop out when a specific year is selected."
      : "");

  render();
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def build_html(payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    data = data.replace("</", "<\\/")  # keep the JSON safe inside a <script> element
    return HTML_HEAD + HTML_BODY + HTML_PAYLOAD.replace(PAYLOAD_MARKER, data) + APP_JS


def main() -> int:
    log("Loading the star schema from Data/clean/ ...")
    payload = build_payload()
    meta = payload["meta"]

    log(f"  order lines embedded : {meta['factRows']:,}")
    log(f"  dated / undated      : {meta['datedRows']:,} / {meta['undatedRows']:,}")
    log(f"  products             : {meta['productCount']:,}")
    log(f"  customers            : {meta['customerCount']:,}")
    log(f"  categories           : {len(payload['categories'])} -> {payload['categories']}")
    log(f"  regions              : {len(payload['regions'])} -> {payload['regions']}")
    log(f"  years                : {payload['years']}")

    log("Generating the self-contained dashboard ...")
    html = build_html(payload)
    if PAYLOAD_MARKER in html:
        raise RuntimeError("payload placeholder was not replaced")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    log(f"  written              : {rel(OUT_FILE)}  ({len(html):,} characters)")
    log("Open the file in a browser - no server and no internet connection required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
