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
  const WORKFLOW_URL =
    "https://github.com/alanqk/multifactor_quant/actions/workflows/run-backtest.yml";
  const TV_EXCHANGE = { NASDAQ: "NASDAQ", NYSE: "NYSE", NYSEARCA: "AMEX", AMEX: "AMEX", ARCA: "AMEX" };

  let equityChart = null;
  let monthChart = null;
  let drawdownChart = null;
  let regimeChart = null;
  let chartToken = 0;
  let tvWidget = null;
  let tvLoader = null;
  let lastFocus = null;

  document.addEventListener("DOMContentLoaded", () => {
    const workflow = $("#backtest-link");
    if (workflow) workflow.href = WORKFLOW_URL;
    $("#run-backtest").addEventListener("click", openBacktest);
    document.addEventListener("click", (event) => {
      const closer = event.target.closest("[data-close]");
      if (!closer) return;
      if (closer.dataset.close === "stock") closeStock();
      if (closer.dataset.close === "backtest") closeBacktest();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!$("#backtest-dialog").hidden) closeBacktest();
      else if (!$("#stock-dialog").hidden) closeStock();
    });
    init();
  });

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
    renderRegime();
    renderMetrics();
    renderRisk();
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
    const previous = ticker;
    month = next;
    const holds = DATA.holdings[month] || [];
    if (!holds.some((row) => row.t === ticker)) ticker = holds[0] ? holds[0].t : ticker;
    $("#month").value = month;
    renderMonth();
    paintMonthChart();
    if (stockIsOpen() && ticker !== previous) mountChart(ticker);
  }

  function setTicker(next, options) {
    const open = !options || options.open !== false;
    const changed = next !== ticker;
    ticker = next;
    renderHoldings();
    renderRanks();
    if (!ticker) return;
    if (!open) {
      if (stockIsOpen()) renderStockFacts();
      return;
    }
    if (!stockIsOpen()) openStock();
    else {
      renderStockFacts();
      if (changed) mountChart(ticker);
      else $("#stock-close").focus();
    }
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
      "。图表读取本目录 data/dash_data.json，不会在浏览器里重跑 Python。要更新数字，用页眉「执行回测」。";
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
    renderRanks();
    renderConcentration();
    if (stockIsOpen()) renderStockFacts();
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
        tickerCell(row.t),
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

  function stockIsOpen() {
    return !$("#stock-dialog").hidden;
  }

  function syncScrollLock() {
    const locked = !$("#stock-dialog").hidden || !$("#backtest-dialog").hidden;
    document.body.classList.toggle("modal-open", locked);
  }

  function openBacktest() {
    $("#backtest-dialog").hidden = false;
    syncScrollLock();
    $("#backtest-link").focus();
  }

  function closeBacktest() {
    $("#backtest-dialog").hidden = true;
    syncScrollLock();
    $("#run-backtest").focus();
  }

  function openStock() {
    if (!ticker) return;
    lastFocus = document.activeElement;
    renderStockFacts();
    $("#stock-dialog").hidden = false;
    syncScrollLock();
    $("#stock-close").focus();
    mountChart(ticker);
  }

  function closeStock() {
    chartToken += 1;
    $("#stock-dialog").hidden = true;
    destroyChart();
    syncScrollLock();
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  function renderStockFacts() {
    const holds = DATA.holdings[month] || [];
    const hold = holds.find((row) => row.t === ticker);
    const name = companyName(ticker);
    const exch = exchangeOf(ticker);
    $("#stock-title").textContent = ticker || "—";
    const bits = [name, exch, sectorName(ticker, hold && hold.sec)].filter((bit) => bit && bit !== "—");
    $("#stock-sub").textContent = bits.join(" · ");
    const px = hold ? hold.p : tickerPx(ticker);
    const items = [
      ["代码", ticker || "—"],
      ["公司", name || "—"],
      ["交易所", exch || "—"],
      ["行业", sectorName(ticker, hold && hold.sec)],
      ["调仓日", month || "—"],
      ["权重", hold ? pct(hold.w) : "未持仓"],
      ["快照价格", num(px, 2)],
      ["合成分", scoreAndRank("combined", hold, "c")],
      ["动量", scoreAndRank("momentum", hold, "m")],
      ["低波动", scoreAndRank("low_vol", hold, "l")],
      ["价值", scoreAndRank("value", hold, "v")],
      ["质量", scoreAndRank("quality", hold, "q")],
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

  function scoreAndRank(name, hold, key) {
    const fromHold = hold && hold[key] != null ? hold[key] : null;
    const score = fromHold != null ? fromHold : factorScore(name, ticker);
    const rank = factorRank(name, ticker);
    const text = num(score, 4);
    if (rank == null) return text;
    const total = ((DATA.factor_ranks[name] && DATA.factor_ranks[name][month]) || []).length;
    return total ? text + " · 第 " + rank + " / " + total : text + " · 第 " + rank;
  }

  function mountChart(symbol) {
    const token = ++chartToken;
    const sym = tvSymbol(symbol);
    destroyChart();
    const status = $("#tv-status");
    status.textContent = "正在加载 TradingView 行情…";
    loadTradingView()
      .then(() => {
        if (token !== chartToken) return;
        if (!window.TradingView || typeof window.TradingView.widget !== "function") {
          throw new Error("TradingView 组件不可用");
        }
        destroyChart();
        const node = document.createElement("div");
        node.id = "tv_widget_" + token;
        node.className = "tv-mount";
        $("#tv-chart").append(node);
        tvWidget = new window.TradingView.widget({
          autosize: true,
          symbol: sym,
          interval: "D",
          timezone: "America/New_York",
          theme: "light",
          style: "1",
          locale: "zh_CN",
          toolbar_bg: "#fbf9f4",
          enable_publishing: false,
          allow_symbol_change: false,
          hide_legend: false,
          save_image: false,
          withdateranges: true,
          container_id: node.id,
        });
        status.textContent =
          "图表由 TradingView 提供（" +
          sym +
          "）。上方价格与因子为 " +
          (month || "所选调仓日") +
          " 的回测快照，与图中实时行情不是同一时点。切换代码会重新加载图表。";
        for (const delay of [700, 1800]) {
          window.setTimeout(() => pruneChartFrames(token), delay);
        }
      })
      .catch(() => {
        if (token !== chartToken) return;
        destroyChart();
        status.replaceChildren();
        status.append(document.createTextNode("TradingView 图表未能加载。可稍后重试，或在新标签页打开行情。"));
        const link = document.createElement("a");
        link.href = "https://www.tradingview.com/chart/?symbol=" + encodeURIComponent(sym);
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "在 TradingView 打开 " + sym;
        status.append(document.createTextNode(" "));
        status.append(link);
      });
  }

  function pruneChartFrames(token) {
    if (token !== chartToken) return;
    const frames = $("#tv-chart").querySelectorAll("iframe");
    for (let i = 0; i < frames.length - 1; i += 1) frames[i].remove();
  }

  function destroyChart() {
    if (tvWidget && typeof tvWidget.remove === "function") {
      try {
        tvWidget.remove();
      } catch (err) {
        /* widget already detached */
      }
    }
    tvWidget = null;
    const host = $("#tv-chart");
    if (host) host.replaceChildren();
  }

  function loadTradingView() {
    if (window.TradingView && typeof window.TradingView.widget === "function") {
      return Promise.resolve();
    }
    if (tvLoader) return tvLoader;
    tvLoader = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://s3.tradingview.com/tv.js";
      script.async = true;
      script.dataset.tvjs = "1";
      script.onload = () => resolve();
      script.onerror = () => {
        tvLoader = null;
        reject(new Error("TradingView 脚本未能加载"));
      };
      document.head.appendChild(script);
    });
    return tvLoader;
  }

  function tvSymbol(symbol) {
    const exch = exchangeOf(symbol);
    if (TV_EXCHANGE[exch]) return TV_EXCHANGE[exch] + ":" + symbol;
    return symbol;
  }

  function companyName(symbol) {
    const info = DATA.tickers && DATA.tickers[symbol];
    if (!info || typeof info !== "object" || !info.name) return "";
    return prettyName(String(info.name));
  }

  function exchangeOf(symbol) {
    const info = DATA.tickers && DATA.tickers[symbol];
    if (!info || typeof info !== "object" || !info.exch) return "";
    return String(info.exch).toUpperCase();
  }

  function prettyName(name) {
    if (!name || name !== name.toUpperCase()) return name;
    return name.toLowerCase().replace(/(^|[^a-z0-9])([a-z])/g, (all, lead, ch) => lead + ch.toUpperCase());
  }

  function factorRank(name, symbol) {
    const rows = (DATA.factor_ranks[name] && DATA.factor_ranks[name][month]) || [];
    const found = rows.find((row) => row.t === symbol);
    return found ? found.r : null;
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
        tickerCell(row.t),
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
    renderDrawdownChart();
    renderRegimeChart();
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
          x: { grid: { display: false }, ticks: { maxRotation: 0, maxTicksLimit: 12 } },
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

  function tickerCell(symbol) {
    const td = document.createElement("td");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ticker-btn";
    btn.textContent = symbol;
    btn.setAttribute("aria-label", "查看 " + symbol + " 行情");
    const name = companyName(symbol);
    if (name) btn.title = name;
    td.append(btn);
    return td;
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
      risk: raw.risk || null,
      drawdown: (raw.drawdown || []).map(asDrawdown),
      market_regime: raw.market_regime || null,
    };
  }

  function renderRegime() {
    const regime = DATA.market_regime;
    const levelNode = $("#regime-level");
    const nameNode = $("#regime-name");
    const capNode = $("#regime-cap");
    const note = $("#regime-note");
    const flag = $("#regime-flag");
    const body = $("#regime-drivers tbody");
    levelNode.className = "regime-level";
    if (!regime) {
      levelNode.textContent = "—";
      nameNode.textContent = "没有市场档位";
      capNode.textContent = "";
      note.textContent = "快照里没有 market_regime。请重新导出看板数据。";
      body.replaceChildren();
      return;
    }
    levelNode.textContent = "L" + regime.level;
    levelNode.classList.add("regime-l" + regime.level);
    nameNode.textContent = regime.label || "";
    nameNode.className = "regime-name regime-l" + regime.level;
    $("#regime-asof").textContent = regime.as_of ? "截至 " + regime.as_of : "";
    const cap = regime.exposure_cap;
    capNode.textContent =
      "建议暴露上限 " +
      pct(cap, 0) +
      " · 综合分 " +
      num(regime.score, 2) +
      " · " +
      (regime.proxy || "");
    note.textContent = regime.note || "";
    const flags = regime.flags || {};
    const bits = [];
    if (flags.rsi_oversold) bits.push("RSI 处于超卖，只作为压力的一部分。");
    if (flags.euphoria) bits.push("乖离偏高，记为轻度亢奋，权重低于压力因子。");
    if (regime.vix_source && regime.vix_source !== "cboe") bits.push("未使用 VIX 文件，波动项是实现波动尖峰。");
    flag.hidden = bits.length === 0;
    flag.textContent = bits.join("");
    body.replaceChildren();
    for (const driver of regime.drivers || []) {
      const tr = document.createElement("tr");
      tr.append(
        cell(driver.name),
        cell(driver.value_label || "—"),
        cell(num(driver.risk, 2), "num"),
        cell(pct(driver.weight, 0), "num"),
        cell(num(driver.contribution, 3), "num")
      );
      body.append(tr);
    }
  }

  function renderRegimeChart() {
    const canvas = $("#regime-chart");
    const regime = DATA.market_regime;
    if (!canvas || typeof Chart === "undefined" || !regime || !(regime.history || []).length) return;
    if (regimeChart) regimeChart.destroy();
    const rows = regime.history;
    regimeChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: rows.map((row) => row.date),
        datasets: [
          {
            label: "档位",
            data: rows.map((row) => row.level),
            borderColor: "#8a5a2a",
            backgroundColor: "rgba(138, 90, 42, 0.12)",
            fill: true,
            stepped: true,
            pointRadius: 0,
            pointHitRadius: 8,
            borderWidth: 2,
          },
        ],
      },
      options: chartOptions({
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                const row = rows[ctx.dataIndex];
                return "L" + ctx.parsed.y + "  分数 " + num(row && row.score, 2);
              },
            },
          },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
          y: {
            min: 1,
            max: 6,
            ticks: { stepSize: 1 },
          },
        },
      }),
    });
  }

  function asDrawdown(row) {
    if (Array.isArray(row)) return { label: row[0], drawdown: row[1] };
    return { label: row.label, drawdown: row.drawdown };
  }

  function renderRisk() {
    const risk = DATA.risk;
    const metrics = $("#risk-metrics");
    const props = $("#risk-props");
    metrics.replaceChildren();
    props.replaceChildren();
    if (!risk) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "这份快照没有 risk 字段。请重新导出 dashboard 数据。";
      metrics.append(empty);
      return;
    }
    const cards = [
      ["最大回撤", pct(risk.max_drawdown), tone(risk.max_drawdown)],
      ["当前回撤", pct(risk.current_drawdown), tone(risk.current_drawdown)],
      ["年化波动", pct(risk.ann_vol), ""],
      ["Sharpe", num(risk.sharpe, 2), ""],
    ];
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
    const rows = [
      ["下行波动", pct(risk.downside_vol)],
      ["Sortino", num(risk.sortino, 3)],
      ["Calmar", num(risk.calmar, 3)],
      ["日胜率", pct(risk.daily_win_rate)],
      ["月胜率", pct(risk.monthly_win_rate)],
      ["盈亏比", num(risk.profit_factor, 3)],
      ["赔率", num(risk.payoff_ratio, 3)],
      ["平均换手(单边)", pct(risk.avg_turnover_one_way)],
      ["回撤低点", risk.max_drawdown_date || "—"],
      ["峰值日期", risk.peak_date || "—"],
      ["回撤熔断", risk.drawdown_halt == null ? "—" : pct(risk.drawdown_halt)],
      ["熔断", risk.drawdown_halt_hit == null ? "—" : risk.drawdown_halt_hit ? "曾触及" : "未触及"],
    ];
    for (const [label, value] of rows) {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      if (label === "熔断" && risk.drawdown_halt_hit) dd.className = "neg";
      wrap.append(dt, dd);
      props.append(wrap);
    }
    const hint = $("#risk-hint");
    const n = risk.monthly_n == null ? "" : "月度样本 " + risk.monthly_n + " 期（不含最后一期没有下一调仓日的占位）。";
    hint.textContent =
      "由同一份样本回测的日收益和净值计算，无风险利率按 0。日胜率与上方命中率相同。盈亏比 = 盈利月合计 / 亏损月绝对值合计；赔率 = 平均盈利月 / 平均亏损月绝对值。" +
      n;
  }

  function renderConcentration() {
    const host = $("#concentration");
    const flag = $("#conc-flag");
    const hint = $("#conc-hint");
    if (!host) return;
    const holds = DATA.holdings[month] || [];
    const weights = holds
      .map((row) => Number(row.w))
      .filter((value) => !Number.isNaN(value))
      .sort((a, b) => b - a);
    const sum = (count) => weights.slice(0, count).reduce((total, value) => total + value, 0);
    const maxWeight = weights.length ? weights[0] : null;
    const cap = DATA.risk && DATA.risk.max_name_weight != null ? Number(DATA.risk.max_name_weight) : null;
    hint.textContent = "调仓日 " + (month || "—") + " · " + weights.length + " 只。前 5 / 前 10 为权重从高到低的合计占比。";
    const items = [
      ["前 5 权重", weights.length ? pct(sum(5)) : "—"],
      ["前 10 权重", weights.length ? pct(sum(10)) : "—"],
      ["最大单票", maxWeight == null ? "—" : pct(maxWeight)],
      ["单票上限", cap == null ? "未配置" : pct(cap)],
    ];
    host.replaceChildren();
    for (const [label, value] of items) {
      const cell = document.createElement("div");
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = value;
      cell.append(span, strong);
      host.append(cell);
    }
    if (!flag) return;
    if (cap == null || maxWeight == null) {
      flag.hidden = true;
      return;
    }
    flag.hidden = false;
    const breached = maxWeight > cap + 0.0005;
    flag.className = breached ? "hint warn" : "hint";
    if (breached) {
      const tooFew = weights.length * cap < 1 - 1e-9;
      flag.textContent = tooFew
        ? "最大单票 " + pct(maxWeight) + " 超过上限 " + pct(cap) + "。等权且 1/持仓数大于上限时，截断后再归一仍会越限。"
        : "最大单票 " + pct(maxWeight) + " 超过上限 " + pct(cap) + "。";
    } else {
      flag.textContent = "最大单票未超过上限 " + pct(cap) + "。";
    }
  }

  function renderDrawdownChart() {
    const canvas = $("#drawdown-chart");
    if (!canvas || typeof Chart === "undefined") return;
    const rows = DATA.drawdown || [];
    if (!rows.length) return;
    if (drawdownChart) drawdownChart.destroy();
    const halt = DATA.risk && DATA.risk.drawdown_halt != null ? DATA.risk.drawdown_halt * 100 : null;
    const labels = rows.map((row) => row.label);
    const datasets = [
      {
        label: "回撤",
        data: rows.map((row) => (row.drawdown == null ? null : row.drawdown * 100)),
        borderColor: "#9c3b2e",
        backgroundColor: "rgba(156, 59, 46, 0.12)",
        fill: true,
        pointRadius: 0,
        pointHitRadius: 8,
        borderWidth: 2,
        tension: 0.15,
      },
    ];
    if (halt != null) {
      datasets.push({
        label: "熔断线",
        data: labels.map(() => halt),
        borderColor: "#8a5a2a",
        pointRadius: 0,
        borderWidth: 1.5,
        borderDash: [4, 4],
        fill: false,
      });
    }
    drawdownChart = new Chart(canvas, {
      type: "line",
      data: { labels, datasets },
      options: chartOptions({
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
          x: { ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
          y: {
            suggestedMax: 0,
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
