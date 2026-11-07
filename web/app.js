/* Static dashboard. Loads ./data/dash_data.json relative to this page so
   GitHub project Pages (/multifactor_quant/) and a local static server both work.
   Accepts the object snapshot in dashboard/dash_data.json and the older
   tuple rows embedded in the Canvas source. */
(function () {
  const FACTORS = [
    ["combined", "合成分"],
    ["momentum", "动量"],
    ["low_vol", "低波动"],
    ["value", "价值"],
    ["quality", "质量"],
  ];

  const MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

  const $ = (sel) => document.querySelector(sel);

  let DATA = null;
  let month = "";
  let factor = "combined";
  let ticker = "";
  let equityChart = null;
  let monthChart = null;

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    try {
      const url = new URL("data/dash_data.json", document.baseURI);
      const res = await fetch(url);
      if (!res.ok) throw new Error("HTTP " + res.status + " " + url.pathname);
      const raw = await res.json();
      DATA = normalize(raw);
      boot();
    } catch (err) {
      const status = $("#status");
      status.classList.add("is-error");
      status.textContent =
        "无法读取 data/dash_data.json（" +
        (err && err.message ? err.message : "未知错误") +
        "）。请从 web/ 目录提供静态文件，例如：python -m http.server -d web 8080";
    }
  }

  function boot() {
    const dates = Object.keys(DATA.holdings);
    month = dates[dates.length - 1] || (DATA.months[DATA.months.length - 1] || {}).date || "";
    const holds = DATA.holdings[month] || [];
    ticker = holds[0] ? holds[0].t : "";

    $("#status").hidden = true;
    $("#app").hidden = false;

    renderIntro();
    renderMetrics();
    renderMonthSelect();
    renderFactorTabs();
    renderMonth();

    $("#month").addEventListener("change", (event) => setMonth(event.target.value));
    $("#heatmap").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-date]");
      if (btn) setMonth(btn.dataset.date);
    });
    $("#holdings tbody").addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (row && row.dataset.ticker) setTicker(row.dataset.ticker);
    });
    $("#ranks tbody").addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (row && row.dataset.ticker) setTicker(row.dataset.ticker);
    });

    requestAnimationFrame(renderCharts);
  }

  function setMonth(next) {
    if (!next || next === month) return;
    month = next;
    const holds = DATA.holdings[month] || [];
    if (!holds.some((row) => row.t === ticker)) ticker = holds[0] ? holds[0].t : ticker;
    $("#month").value = month;
    renderMonth();
    paintMonthChart();
  }

  function setTicker(next) {
    ticker = next;
    renderHoldings();
    renderDetail();
    renderRanks();
  }

  function renderIntro() {
    const meta = DATA.meta || {};
    const stats = DATA.stats || {};
    $("#kicker").textContent =
      "Multifactor · " + (meta.universe || "DJIA-30");
    $("#asof").textContent = meta.as_of ? "数据截至 " + meta.as_of : "";
    $("#lede").textContent =
      "静态回放已发布的样本回测：月末调仓、" +
      labelize(meta.weighting) +
      "、多头 " +
      pct(meta.long_pct, 0) +
      "。图表读取本目录 data/dash_data.json，不会在浏览器里重跑 Python。";
    $("#note").textContent = meta.note ? "数据附注：" + meta.note : "";
    if (stats.end) document.title = "多因子回测看板 · " + stats.end;
  }

  function renderMetrics() {
    const s = DATA.stats;
    const cards = [
      ["CAGR", pctSigned(s.cagr), tone(s.cagr)],
      ["Sharpe", num(s.sharpe, 2), ""],
      ["MaxDD", pct(s.max_drawdown), tone(s.max_drawdown)],
      ["年化波动", pct(s.ann_vol), ""],
    ];
    const metrics = $("#metrics");
    metrics.replaceChildren();
    for (const [label, value, klass] of cards) {
      const card = document.createElement("article");
      card.className = "metric" + (klass ? " " + klass : "");
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = value;
      card.append(span, strong);
      metrics.append(card);
    }

    const meta = DATA.meta || {};
    const props = [
      ["区间", (s.start || "—") + " → " + (s.end || "—")],
      ["年数", num(s.years, 2)],
      ["总收益", pctSigned(s.total_return)],
      ["期末净值", money(s.final_equity)],
      ["命中率", pct(s.hit_rate)],
      ["平均换手(单边)", pct(s.avg_turnover_one_way)],
      ["信息比率", num(s.information_ratio, 3)],
      ["IC 均值", num(s.ic_mean, 4)],
      ["IC IR", num(s.ic_ir, 3)],
      ["IC 样本数", s.ic_n == null ? "—" : String(s.ic_n)],
      ["Sortino", num(s.sortino, 3)],
      ["Calmar", num(s.calmar, 3)],
      ["股票池", meta.universe || "—"],
      ["调仓", labelize(meta.rebalance)],
      ["多头占比", pct(meta.long_pct, 0)],
      ["加权", labelize(meta.weighting)],
    ];
    const dl = $("#props");
    dl.replaceChildren();
    for (const [label, value] of props) {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      if (label === "信息比率") dd.className = tone(s.information_ratio);
      if (label === "总收益") dd.className = tone(s.total_return);
      wrap.append(dt, dd);
      dl.append(wrap);
    }
  }

  function renderMonthSelect() {
    const select = $("#month");
    select.replaceChildren();
    const dates = Object.keys(DATA.holdings);
    const source = dates.length ? dates : DATA.months.map((row) => row.date);
    for (const date of source) {
      const option = document.createElement("option");
      option.value = date;
      option.textContent = date;
      select.append(option);
    }
    select.value = month;
  }

  function renderFactorTabs() {
    const tabs = $("#factor-tabs");
    tabs.replaceChildren();
    for (const [key, label] of FACTORS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.role = "tab";
      btn.dataset.factor = key;
      btn.textContent = label;
      btn.setAttribute("aria-selected", key === factor ? "true" : "false");
      btn.addEventListener("click", () => {
        factor = key;
        for (const other of tabs.querySelectorAll("button")) {
          other.setAttribute("aria-selected", other === btn ? "true" : "false");
        }
        renderRanks();
      });
      tabs.append(btn);
    }
  }

  function renderMonth() {
    renderMonthStats();
    renderHeatmap();
    renderHoldings();
    renderDetail();
    renderRanks();
  }

  function currentMonthRow() {
    return DATA.months.find((row) => row.date === month) || null;
  }

  function renderMonthStats() {
    const row = currentMonthRow();
    const host = $("#month-stats");
    host.replaceChildren();
    const items = row
      ? [
          ["策略月收益", pctSigned(row.month_return), tone(row.month_return)],
          ["基准月收益", pctSigned(row.bench_return), tone(row.bench_return)],
          ["主动收益", pctSigned(row.active), tone(row.active)],
          ["换手(单边)", pct(row.turnover), ""],
          ["持仓数", row.n_hold == null ? "—" : String(row.n_hold), ""],
          ["IC", num(row.ic, 4), ""],
          ["月末净值", money(row.equity), ""],
        ]
      : [["当月", "该调仓日没有月度指标", ""]];
    for (const [label, value, klass] of items) {
      const cell = document.createElement("div");
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = value;
      if (klass) strong.className = klass;
      cell.append(span, strong);
      host.append(cell);
    }
  }

  function renderHeatmap() {
    const host = $("#heatmap");
    host.replaceChildren();
    const byYear = new Map();
    for (const day of DATA.calendar) {
      const year = String(day.date).slice(0, 4);
      if (!byYear.has(year)) byYear.set(year, []);
      byYear.get(year).push(day);
    }
    for (const [year, days] of byYear) {
      const block = document.createElement("div");
      block.className = "heat-year";
      const label = document.createElement("span");
      label.textContent = year;
      const row = document.createElement("div");
      row.className = "heat-row";
      for (const day of days) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "heat" + (day.date === month ? " is-selected" : "");
        btn.dataset.date = day.date;
        btn.style.background = heatColor(day.value);
        btn.title = day.date;
        const name = document.createElement("span");
        name.className = "heat-m";
        const monthIndex = Number(String(day.date).slice(5, 7)) - 1;
        name.textContent = MONTH_NAMES[monthIndex] || day.date;
        const value = document.createElement("span");
        value.className = "heat-v";
        value.textContent = signedPoints(day.value);
        btn.append(name, value);
        row.append(btn);
      }
      block.append(label, row);
      host.append(block);
    }
  }

  function renderHoldings() {
    const holds = DATA.holdings[month] || [];
    $("#hold-count").textContent = holds.length ? holds.length + " 只" : "";
    const body = $("#holdings tbody");
    body.replaceChildren();
    for (const row of holds) {
      const tr = document.createElement("tr");
      tr.dataset.ticker = row.t;
      if (row.t === ticker) tr.classList.add("is-selected");
      tr.append(
        cell(row.t),
        cell(pct(row.w), "num"),
        cell(num(row.c, 4), "num"),
        cell(num(row.p, 2), "num"),
        cell(sectorName(row.t, row.sec))
      );
      body.append(tr);
    }
    if (!holds.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "该月没有持仓记录";
      tr.append(td);
      body.append(tr);
    }
  }

  function renderDetail() {
    const holds = DATA.holdings[month] || [];
    const hold = holds.find((row) => row.t === ticker);
    const px = hold ? hold.p : tickerPx(ticker);
    const items = [
      ["代码", ticker || "—"],
      ["行业", sectorName(ticker, hold && hold.sec)],
      ["权重", hold ? pct(hold.w) : "—"],
      ["价格", num(px, 2)],
      ["合成分", num(hold ? hold.c : factorScore("combined", ticker), 4)],
      ["动量", num(hold ? hold.m : factorScore("momentum", ticker), 4)],
      ["低波动", num(hold ? hold.l : factorScore("low_vol", ticker), 4)],
      ["价值", num(hold ? hold.v : factorScore("value", ticker), 4)],
      ["质量", num(hold ? hold.q : factorScore("quality", ticker), 4)],
    ];
    const dl = $("#detail");
    dl.replaceChildren();
    for (const [label, value] of items) {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      wrap.append(dt, dd);
      dl.append(wrap);
    }
  }

  function renderRanks() {
    const rows = (DATA.factor_ranks[factor] && DATA.factor_ranks[factor][month]) || [];
    const body = $("#ranks tbody");
    body.replaceChildren();
    const ordered = rows.slice().sort((a, b) => a.r - b.r);
    for (const row of ordered) {
      const tr = document.createElement("tr");
      tr.dataset.ticker = row.t;
      if (row.h === 1) tr.classList.add("is-held");
      if (row.t === ticker) tr.classList.add("is-selected");
      const held = document.createElement("td");
      if (row.h === 1) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = "持仓";
        held.append(badge);
      } else {
        held.textContent = "—";
      }
      tr.append(
        cell(String(row.r), "num"),
        cell(row.t),
        cell(num(row.s, 4), "num"),
        held,
        cell(sectorName(row.t, row.sec))
      );
      body.append(tr);
    }
  }

  function renderCharts() {
    const last = DATA.equity[DATA.equity.length - 1];
    const host = $("#end-multiples");
    host.replaceChildren();
    if (last) {
      host.append(
        textNode("期末 "),
        emphasis(num(last.strategy, 2), "strat"),
        textNode(" 策略  ·  "),
        emphasis(num(last.benchmark, 2), "bench"),
        textNode(" 基准")
      );
    }
    if (typeof Chart === "undefined") {
      $("#chart-fallback").hidden = false;
      return;
    }
    Chart.defaults.font.family = '"IBM Plex Sans", "Segoe UI", sans-serif';
    Chart.defaults.color = "#5e574c";
    Chart.defaults.borderColor = "rgba(28, 25, 21, 0.08)";
    renderEquityChart();
    renderMonthChart();
  }

  function renderEquityChart() {
    const labels = DATA.equity.map((row) => row.label);
    equityChart = new Chart($("#equity-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "策略",
            data: DATA.equity.map((row) => row.strategy),
            borderColor: "#1f6b4a",
            backgroundColor: "rgba(31, 107, 74, 0.10)",
            fill: true,
            pointRadius: 0,
            pointHitRadius: 10,
            borderWidth: 2,
            tension: 0.18,
          },
          {
            label: "等权基准",
            data: DATA.equity.map((row) => row.benchmark),
            borderColor: "#3d5a80",
            pointRadius: 0,
            pointHitRadius: 10,
            borderWidth: 2,
            borderDash: [5, 4],
            tension: 0.18,
          },
        ],
      },
      options: chartOptions({
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 18 } },
          tooltip: {
            callbacks: {
              label(ctx) {
                return ctx.dataset.label + "  " + num(ctx.parsed.y, 3);
              },
            },
          },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
          y: {
            ticks: {
              callback(value) {
                return num(value, 2);
              },
            },
          },
        },
      }),
    });
  }

  function renderMonthChart() {
    monthChart = new Chart($("#month-chart"), {
      type: "bar",
      data: {
        labels: DATA.months.map((row) => row.month || row.date),
        datasets: [
          {
            label: "策略",
            data: DATA.months.map((row) => row.month_return * 100),
            backgroundColor: monthBarColors("#1f6b4a"),
            borderColor: "#1c1915",
            borderWidth: monthBorderWidths(),
            borderRadius: 4,
          },
          {
            label: "基准",
            data: DATA.months.map((row) => row.bench_return * 100),
            backgroundColor: "rgba(61, 90, 128, 0.55)",
            borderRadius: 4,
          },
        ],
      },
      options: chartOptions({
        onClick(_evt, elements) {
          if (!elements.length) return;
          const row = DATA.months[elements[0].index];
          if (row) setMonth(row.date);
        },
        onHover(evt, elements) {
          evt.native.target.style.cursor = elements.length ? "pointer" : "default";
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 18 } },
          tooltip: {
            callbacks: {
              label(ctx) {
                return ctx.dataset.label + "  " + signedPoints(ctx.parsed.y);
              },
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0 } },
          y: {
            ticks: {
              callback(value) {
                return value + "%";
              },
            },
          },
        },
      }),
    });
  }

  function paintMonthChart() {
    if (!monthChart) return;
    monthChart.data.datasets[0].backgroundColor = monthBarColors("#1f6b4a");
    monthChart.data.datasets[0].borderWidth = monthBorderWidths();
    monthChart.update();
  }

  function selectedMonthIndex() {
    return DATA.months.findIndex((row) => row.date === month);
  }

  function monthBarColors(hex) {
    const selected = selectedMonthIndex();
    return DATA.months.map((_, index) => (index === selected ? hex : "rgba(31, 107, 74, 0.45)"));
  }

  function monthBorderWidths() {
    const selected = selectedMonthIndex();
    return DATA.months.map((_, index) => (index === selected ? 2 : 0));
  }

  function chartOptions(extra) {
    return Object.assign(
      {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
      },
      extra
    );
  }

  function factorScore(name, symbol) {
    const rows = (DATA.factor_ranks[name] && DATA.factor_ranks[name][month]) || [];
    const found = rows.find((row) => row.t === symbol);
    return found ? found.s : null;
  }

  function sectorName(symbol, fallback) {
    const info = DATA.tickers && DATA.tickers[symbol];
    if (typeof info === "string" && info) return info;
    if (info && typeof info === "object" && info.sec) return info.sec;
    return fallback || "—";
  }

  function tickerPx(symbol) {
    const info = DATA.tickers && DATA.tickers[symbol];
    if (info && typeof info === "object" && info.px != null) return info.px;
    return null;
  }

  function cell(text, className) {
    const td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    return td;
  }

  function textNode(text) {
    return document.createTextNode(text);
  }

  function emphasis(text, className) {
    const node = document.createElement("b");
    node.className = className;
    node.textContent = text;
    return node;
  }

  function normalize(raw) {
    if (!raw || typeof raw !== "object") throw new Error("数据不是 JSON 对象");
    for (const key of ["stats", "equity", "holdings"]) {
      if (raw[key] == null) throw new Error("缺少字段 " + key);
    }
    return {
      meta: raw.meta || {},
      stats: raw.stats,
      equity: (raw.equity || []).map(asEquity),
      months: (raw.months || []).map(asMonth),
      calendar: (raw.calendar || []).map(asCalendar),
      holdings: mapRows(raw.holdings, asHold),
      factor_ranks: mapFactors(raw.factor_ranks),
      tickers: raw.tickers || {},
    };
  }

  function mapRows(table, cast) {
    const out = {};
    for (const [key, rows] of Object.entries(table || {})) out[key] = (rows || []).map(cast);
    return out;
  }

  function mapFactors(table) {
    const out = {};
    for (const [name, byMonth] of Object.entries(table || {})) out[name] = mapRows(byMonth, asRank);
    return out;
  }

  function asEquity(row) {
    if (Array.isArray(row)) return { label: row[0], strategy: row[1], benchmark: row[2] };
    return { label: row.label, strategy: row.strategy, benchmark: row.benchmark };
  }

  function asMonth(row) {
    if (Array.isArray(row)) {
      return {
        date: row[0],
        month: row[1],
        n_hold: row[2],
        turnover: row[3],
        month_return: row[4],
        bench_return: row[5],
        active: row[6],
        equity: row[7],
        ic: row[8],
      };
    }
    return row;
  }

  function asHold(row) {
    if (Array.isArray(row)) {
      return { t: row[0], w: row[1], c: row[2], m: row[3], l: row[4], v: row[5], q: row[6], p: row[7] };
    }
    return row;
  }

  function asRank(row) {
    if (Array.isArray(row)) return { t: row[0], s: row[1], r: row[2], h: row[3] };
    return row;
  }

  function asCalendar(row) {
    if (Array.isArray(row)) return { date: row[0], value: row[1] };
    return row;
  }

  function pct(x, digits) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    return (Number(x) * 100).toFixed(digits == null ? 2 : digits) + "%";
  }

  function pctSigned(x, digits) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    const value = Number(x) * 100;
    const d = digits == null ? 2 : digits;
    return (value > 0 ? "+" : "") + value.toFixed(d) + "%";
  }

  function signedPoints(x) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    const value = Number(x);
    return (value > 0 ? "+" : "") + value.toFixed(2) + "%";
  }

  function num(x, digits) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    return Number(x).toFixed(digits == null ? 2 : digits);
  }

  function money(x) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    return Number(x).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  function tone(x) {
    if (x == null || Number.isNaN(Number(x)) || Number(x) === 0) return "";
    return Number(x) > 0 ? "pos" : "neg";
  }

  function labelize(value) {
    const map = { equal: "等权", score: "按分数", "month-end": "月末", M: "月末" };
    return map[value] || value || "—";
  }

  function heatColor(value) {
    if (value == null || Number.isNaN(Number(value)) || Math.abs(Number(value)) < 0.05) return "#efe8da";
    const t = Math.max(-1, Math.min(1, Number(value) / 6));
    const alpha = 0.18 + 0.72 * Math.abs(t);
    return t > 0
      ? "rgba(31, 107, 74, " + alpha.toFixed(3) + ")"
      : "rgba(156, 59, 46, " + alpha.toFixed(3) + ")";
  }
})();
