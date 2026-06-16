const demoResults = [
  { company: "Reliance Industries", symbol: "RELIANCE", exchange: "NSE", date: "2026-06-08", quarter: "Q1 FY27", status: "estimated" },
  { company: "Tata Consultancy Services", symbol: "TCS", exchange: "NSE", date: "2026-06-09", quarter: "Q1 FY27", status: "confirmed" },
  { company: "HDFC Bank", symbol: "HDFCBANK", exchange: "NSE", date: "2026-06-12", quarter: "Q1 FY27", status: "confirmed" },
  { company: "Infosys", symbol: "INFY", exchange: "NSE", date: "2026-06-15", quarter: "Q1 FY27", status: "estimated" },
  { company: "ICICI Bank", symbol: "ICICIBANK", exchange: "BSE", date: "2026-06-18", quarter: "Q1 FY27", status: "confirmed" },
  { company: "Hindustan Unilever", symbol: "HINDUNILVR", exchange: "NSE", date: "2026-06-22", quarter: "Q1 FY27", status: "estimated" },
  { company: "Bharti Airtel", symbol: "BHARTIARTL", exchange: "BSE", date: "2026-07-03", quarter: "Q1 FY27", status: "confirmed" },
  { company: "State Bank of India", symbol: "SBIN", exchange: "NSE", date: "2026-07-10", quarter: "Q1 FY27", status: "estimated" }
];

const storageKey = "quarterwatch-results-v1";
const watchKey = "quarterwatch-watchlist-v1";
const settingsKey = "quarterwatch-settings-v1";
const generatedFeedUrl = "data/results.json";
const newsFeedUrl = "data/news.json";
const financialsFeedUrl = "data/financials.json";
const marketNewsFeedUrl = "data/market-news.json";
const stockAnalysisFeedUrl = "data/stock-analysis.json";
const practicePricesFeedUrl = "data/practice-prices.json";
const watchPredictionsFeedUrl = "data/watch-predictions.json";
const marketOverviewFeedUrl = "data/market-overview.json";
const practicePositionsKey = "stockscope-practice-positions-v1";
const practiceHistoryKey = "stockscope-practice-history-v1";
let results = JSON.parse(localStorage.getItem(storageKey) || "null") || demoResults;
let newsItems = [];
let financialItems = [];
let marketNewsItems = [];
let stockAnalysisItems = [];
let practicePrices = [];
let watchPredictionData = { today: [], tomorrow: [] };
let marketOverviewData = { instruments: [], components: {} };
let verificationData = { levels: {}, recentJobs: [] };
let currentUser = null;
let practicePositions = JSON.parse(localStorage.getItem(practicePositionsKey) || "[]");
let practiceHistory = JSON.parse(localStorage.getItem(practiceHistoryKey) || "[]");
let watchlist = new Set(JSON.parse(localStorage.getItem(watchKey) || "[]"));
let view = "list";
let calendarDate = new Date();
let jobPollTimer = null;
let activeCompany = null;
let activeStockProfile = null;
let companyProfileStatus = "idle";
let activeAnalysis = null;
let companyNewsAnalysis = null;
let companyFundamentals = null;
let companyFundamentalsRequest = 0;
let companyChartRange = "1D";

const $ = (id) => document.getElementById(id);
const today = new Date();
today.setHours(0, 0, 0, 0);

function localDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function dateKey(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function save() {
  localStorage.setItem(storageKey, JSON.stringify(results));
  localStorage.setItem(watchKey, JSON.stringify([...watchlist]));
}

function companyKey(exchange, symbol) {
  return `${exchange}:${symbol}`;
}

function isWatched(item) {
  return watchlist.has(companyKey(item.exchange, item.symbol)) || watchlist.has(item.symbol);
}

function toggleWatchlist(item) {
  const key = companyKey(item.exchange, item.symbol);
  const watched = isWatched(item);
  watchlist.delete(item.symbol);
  watched ? watchlist.delete(key) : watchlist.add(key);
  save();
  toast(watched ? `${item.company} removed from watchlist` : `${item.company} added to watchlist`);
}

function initials(name) {
  return name.split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

function safeUrl(value) {
  try {
    const url = new URL(value, location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function formatDate(value) {
  return localDate(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function companyIndex() {
  const companies = new Map();
  for (const item of [...financialItems, ...newsItems, ...results]) {
    const key = `${item.exchange}:${item.symbol}`;
    if (!companies.has(key)) companies.set(key, { company: item.company, symbol: item.symbol, exchange: item.exchange });
  }
  return [...companies.values()].sort((a, b) => a.company.localeCompare(b.company));
}

function renderCompanySearch() {
  const term = $("searchInput").value.trim().toLowerCase();
  if (!term) {
    $("companySearchResults").hidden = true;
    return;
  }
  const matches = companyIndex().filter(item => item.company.toLowerCase().includes(term) || item.symbol.toLowerCase().includes(term)).slice(0, 20);
  $("companySearchResults").innerHTML = matches.map(item => `<button class="search-result" data-search-symbol="${escapeHtml(item.symbol)}" data-search-exchange="${escapeHtml(item.exchange)}"><span><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.symbol)}</small></span><small>${escapeHtml(item.exchange)}</small></button>`).join("");
  $("companySearchResults").hidden = matches.length === 0;
}

function filteredResults() {
  const term = $("searchInput").value.trim().toLowerCase();
  const exchange = $("exchangeFilter").value;
  const status = $("statusFilter").value;
  return results.filter(item => {
    const matchesTerm = !term || item.company.toLowerCase().includes(term) || item.symbol.toLowerCase().includes(term);
    return matchesTerm && (!exchange || item.exchange === exchange) && (!status || item.status === status) && (view !== "watchlist" || isWatched(item));
  }).sort((a, b) => a.date.localeCompare(b.date));
}

function renderMetrics() {
  const weekEnd = new Date(today); weekEnd.setDate(weekEnd.getDate() + 7);
  const month = today.getMonth(), year = today.getFullYear();
  $("weekCount").textContent = results.filter(r => localDate(r.date) >= today && localDate(r.date) <= weekEnd).length;
  $("estimatedCount").textContent = results.filter(r => r.status === "estimated").length;
  $("watchlistCount").textContent = companyIndex().filter(isWatched).length;
  $("totalCount").textContent = companyIndex().length.toLocaleString("en-IN");
}

function renderTable() {
  const items = filteredResults();
  const official = items.filter(item => item.verificationLevel === "official-exchange").length;
  $("resultSummary").textContent = `${items.length} result date${items.length === 1 ? "" : "s"} shown · ${official} exchange verified`;
  $("emptyState").hidden = items.length > 0;
  $("resultsBody").innerHTML = items.map(item => `
    <tr data-company-symbol="${escapeHtml(item.symbol)}" data-company-exchange="${escapeHtml(item.exchange)}">
      <td data-label="Company"><div class="company-cell"><span class="company-logo">${escapeHtml(initials(item.company))}</span><div><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.symbol)}</small></div></div></td>
      <td data-label="Result date" class="date-cell"><strong>${formatDate(item.date)}</strong><small>${localDate(item.date).toLocaleDateString("en-IN", { weekday: "long" })}</small></td>
      <td data-label="Quarter">${escapeHtml(item.quarter)}</td><td data-label="Exchange">${escapeHtml(item.exchange)}</td>
      <td data-label="Status"><span class="badge ${item.status}">${item.status === "confirmed" ? "●" : "◷"} ${item.status}</span><span class="verification-badge ${escapeHtml(item.verificationLevel || "legacy-unverified")}">${escapeHtml(item.verificationLevel === "official-exchange" ? "NSE verified" : item.verificationLevel === "external-feed" ? "External source" : "Legacy")}</span></td>
      <td data-label="Watchlist"><button class="text-button star ${isWatched(item) ? "active" : ""}" data-star="${escapeHtml(item.symbol)}" data-star-exchange="${escapeHtml(item.exchange)}" aria-label="Toggle watchlist">★</button></td>
    </tr>`).join("");
}

function renderCompanyDirectory() {
  const term = $("searchInput").value.trim().toLowerCase();
  const exchange = $("exchangeFilter").value;
  const companies = companyIndex().filter(item => (!term || `${item.company} ${item.symbol}`.toLowerCase().includes(term)) && (!exchange || item.exchange === exchange) && (view !== "watchlist" || isWatched(item)));
  const financialByCompany = new Map(financialItems.map(item => [`${item.exchange}:${item.symbol}`, item]));
  const resultByCompany = new Map(results.map(item => [`${item.exchange}:${item.symbol}`, item]));
  const filingCounts = new Map();
  newsItems.forEach(item => {
    const key = `${item.exchange}:${item.symbol}`;
    filingCounts.set(key, (filingCounts.get(key) || 0) + 1);
  });
  $("companyDirectorySummary").textContent = view === "watchlist" ? `${companies.length.toLocaleString("en-IN")} saved companies` : `${companies.length.toLocaleString("en-IN")} companies indexed`;
  $("companyDirectoryBody").innerHTML = companies.slice(0, 1500).map(item => {
    const key = `${item.exchange}:${item.symbol}`;
    const financial = financialByCompany.get(key);
    const filings = filingCounts.get(key) || 0;
    const upcoming = resultByCompany.get(key);
    return `<tr data-directory-symbol="${escapeHtml(item.symbol)}" data-directory-exchange="${escapeHtml(item.exchange)}"><td data-label="Company"><div class="company-cell"><span class="company-logo">${escapeHtml(initials(item.company))}</span><div><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.symbol)}</small></div></div></td><td data-label="Exchange">${escapeHtml(item.exchange)}</td><td data-label="Latest quarter">${financial ? escapeHtml(financial.quarter) : "—"}</td><td data-label="Recent filings">${filings}</td><td data-label="Upcoming result">${upcoming ? formatDate(upcoming.date) : "Not announced"}</td></tr>`;
  }).join("");
}

function renderCalendar() {
  const year = calendarDate.getFullYear(), month = calendarDate.getMonth();
  $("calendarTitle").textContent = calendarDate.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  const selected = filteredResults();
  $("calendarGrid").innerHTML = Array.from({ length: 42 }, (_, i) => {
    const day = new Date(start); day.setDate(start.getDate() + i);
    const key = dateKey(day);
    const events = selected.filter(item => item.date === key);
    const classes = ["calendar-day", day.getMonth() !== month ? "muted" : "", key === dateKey(today) ? "today" : ""].join(" ");
    return `<div class="${classes}"><span class="day-number">${day.getDate()}</span>${events.slice(0, 3).map(event => `<div class="calendar-event" title="${escapeHtml(event.company)}">${escapeHtml(event.symbol)}</div>`).join("")}${events.length > 3 ? `<div class="calendar-event">+${events.length - 3} more</div>` : ""}</div>`;
  }).join("");
}

function filteredNews() {
  const term = $("searchInput").value.trim().toLowerCase();
  const exchange = $("exchangeFilter").value;
  return newsItems.filter(item => {
    const searchable = `${item.company} ${item.symbol} ${item.headline} ${item.summary}`.toLowerCase();
    return (!term || searchable.includes(term)) && (!exchange || item.exchange === exchange);
  });
}

function renderNews() {
  const items = filteredNews();
  const shown = items.slice(0, 500);
  $("newsSummary").textContent = `${items.length} item${items.length === 1 ? "" : "s"} found${items.length > shown.length ? ` · showing latest ${shown.length}` : ""}`;
  $("newsEmptyState").hidden = items.length > 0;
  $("newsList").innerHTML = shown.map(item => {
    const published = new Date(item.publishedAt);
    const sourceUrl = safeUrl(item.url);
    const link = sourceUrl ? `<a class="news-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">Open source</a>` : "";
    return `<article class="news-item" data-news-symbol="${escapeHtml(item.symbol)}" data-news-exchange="${escapeHtml(item.exchange)}">
      <div class="news-company"><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.symbol)} · ${escapeHtml(item.exchange)}</small></div>
      <div class="news-copy"><span class="news-type">${escapeHtml(item.type)}</span><h3>${escapeHtml(item.headline)}</h3>${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}<span class="news-time">${published.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span></div>
      ${link}
    </article>`;
  }).join("");
}

function renderMarketNews() {
  const platform = $("marketNewsPlatform").value;
  const items = marketNewsItems.filter(item => !platform || (platform === "stock" ? item.matchedCompany : item.platform === platform));
  const latest = [...items];
  const stockCount = items.filter(item => item.matchedCompany).length;
  $("marketNewsSummary").textContent = `${stockCount} stock-specific stories · ${items.length} total · ${new Set(items.map(item => item.source)).size} sources`;
  $("trendingNews").innerHTML = items.slice(0, 3).map(item => `<article class="trending-card"><span class="trend-score">${item.matchedCompany ? `${escapeHtml(item.matchedCompany.symbol)} · ${escapeHtml(item.impact)}` : `Market · trend ${item.trendScore}`}</span><div><p>${escapeHtml(item.source)} · ${new Date(item.publishedAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p><h3>${escapeHtml(item.title)}</h3></div><div class="story-actions">${item.matchedCompany ? `<button class="story-company-link" data-market-symbol="${escapeHtml(item.matchedCompany.symbol)}" data-market-exchange="${escapeHtml(item.matchedCompany.exchange)}">View company</button>` : ""}<a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener">Read story →</a></div></article>`).join("") || `<div class="empty-state"><strong>No prioritized stories</strong><span>Run the market news job to update.</span></div>`;
  $("latestMarketNews").innerHTML = latest.slice(0, 100).map(item => `<article class="market-news-item"><div><span class="signal-tag ${item.matchedCompany ? "positive" : item.platform === "social" ? "positive" : "neutral"}">${escapeHtml(item.matchedCompany ? item.impact : item.platform)}</span><p class="market-news-meta">${escapeHtml(item.matchedCompany ? `${item.matchedCompany.symbol} · ${item.source}` : item.source)}</p></div><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || "")}</p><span class="market-news-meta">${new Date(item.publishedAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} · priority ${item.stockPriority || 0} · trend ${item.trendScore}</span></div><div>${item.matchedCompany ? `<button class="text-button" data-market-symbol="${escapeHtml(item.matchedCompany.symbol)}" data-market-exchange="${escapeHtml(item.matchedCompany.exchange)}">View company</button>` : ""}<a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener">Open source</a></div></article>`).join("");
}

function renderStockAnalysis() {
  const signal = $("stockSignalFilter").value;
  const items = stockAnalysisItems.filter(item => !signal || item.signal === signal);
  $("stockAnalysisSummary").textContent = `${items.length} analyzed stocks · updated from daily OHLCV`;
  $("stockAnalysisCards").innerHTML = items.map(item => `<article class="analysis-card" data-analysis-symbol="${escapeHtml(item.symbol)}" data-analysis-exchange="${escapeHtml(item.exchange)}"><div class="analysis-card-heading"><div><h3>${escapeHtml(item.company)}</h3><p>${escapeHtml(item.symbol)} · ${escapeHtml(item.exchange)} · ${escapeHtml(item.asOf)}</p></div><strong>₹${Number(item.close).toLocaleString("en-IN")}</strong></div><div class="analysis-signal"><strong class="${escapeHtml(item.signal)}">${escapeHtml(item.signal)}</strong><span>${item.confidence}% indicator agreement</span></div><div class="analysis-metrics"><div class="analysis-metric"><small>RSI 14</small><strong>${item.rsi14 ?? "—"}</strong></div><div class="analysis-metric"><small>20d momentum</small><strong>${item.momentum20d ?? "—"}%</strong></div><div class="analysis-metric"><small>Volatility</small><strong>${item.annualizedVolatility ?? "—"}%</strong></div><div class="analysis-metric"><small>Support</small><strong>₹${item.support20d}</strong></div><div class="analysis-metric"><small>Resistance</small><strong>₹${item.resistance20d}</strong></div><div class="analysis-metric"><small>Volume ratio</small><strong>${item.volumeRatio ?? "—"}x</strong></div></div></article>`).join("") || `<div class="empty-state"><strong>No stock analysis available</strong><span>Run the daily stock analysis job.</span></div>`;
}

function marketSparkline(chart, positive) {
  if (!chart?.length) return "";
  const values = chart.map(row => Number(row.close));
  const low = Math.min(...values), high = Math.max(...values), spread = high - low || 1;
  const points = values.map((value, index) => `${(index / Math.max(1, values.length - 1) * 240).toFixed(1)},${(65 - (value - low) / spread * 55).toFixed(1)}`).join(" ");
  return `<svg class="market-sparkline" viewBox="0 0 240 70" aria-hidden="true"><polyline class="${positive ? "up" : "down"}" points="${points}"></polyline></svg>`;
}

function marketChange(value) {
  if (value === null || value === undefined) return `<span>—</span>`;
  const tone = Number(value) >= 0 ? "positive" : "negative";
  return `<span class="${tone}">${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}%</span>`;
}

function renderMarketOverview() {
  const type = $("marketInstrumentFilter").value;
  const items = (marketOverviewData.instruments || []).filter(item => !type || item.type === type);
  $("marketOverviewSummary").textContent = `${items.length} instruments · updated ${marketOverviewData.updatedAt ? new Date(marketOverviewData.updatedAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "not yet"}`;
  $("marketInstrumentCards").innerHTML = items.map(item => `<article class="market-instrument-card">
    <div class="market-instrument-heading"><div><span class="signal-tag neutral">${escapeHtml(item.type)}</span><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.market)} · ${escapeHtml(item.symbol)} · ${escapeHtml(item.asOf || "")}</p></div><strong>${Number(item.price).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></div>
    ${marketSparkline(item.chart, Number(item.change1m) >= 0)}
    <div class="market-change-grid"><div><small>1 day</small>${marketChange(item.change1d)}</div><div><small>1 week</small>${marketChange(item.change1w)}</div><div><small>1 month</small>${marketChange(item.change1m)}</div></div>
    <div class="market-range"><span>1m low ${Number(item.rangeLow).toLocaleString("en-IN")}</span><span>1m high ${Number(item.rangeHigh).toLocaleString("en-IN")}</span></div>
    <a href="${escapeHtml(safeUrl(item.sourceUrl))}" target="_blank" rel="noopener">Open market chart</a>
  </article>`).join("") || `<div class="empty-state"><strong>No market overview available</strong><span>Run the market overview job.</span></div>`;

  const componentNames = Object.keys(marketOverviewData.components || {});
  const current = $("componentIndexSelect").value;
  $("componentIndexSelect").innerHTML = componentNames.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  $("componentIndexSelect").value = componentNames.includes(current) ? current : componentNames[0] || "";
  renderMarketComponents();
  if (marketOverviewData.disclaimer) $("marketOverviewDisclaimer").textContent = marketOverviewData.disclaimer;
}

function renderMarketComponents() {
  const indexName = $("componentIndexSelect").value;
  const rows = marketOverviewData.components?.[indexName] || [];
  $("marketComponentsSummary").textContent = `${rows.length} current ${indexName || "index"} components`;
  $("marketComponentsBody").innerHTML = rows.map(item => `<tr data-component-symbol="${escapeHtml(item.symbol)}"><td data-label="Company"><div class="company-cell"><span class="company-logo">${escapeHtml(initials(item.company))}</span><div><strong>${escapeHtml(item.company)}</strong><small>${escapeHtml(item.symbol)}</small></div></div></td><td data-label="Last price">${item.lastPrice == null ? "—" : `₹${Number(item.lastPrice).toLocaleString("en-IN")}`}</td><td data-label="Daily change">${marketChange(item.pChange)}</td><td data-label="Volume">${item.volume == null ? "—" : Number(item.volume).toLocaleString("en-IN")}</td><td data-label="Free-float market cap">${item.marketCap == null ? "—" : Number(item.marketCap).toLocaleString("en-IN")}</td></tr>`).join("") || `<tr><td colspan="5"><div class="empty-state"><strong>No components available</strong><span>NSE may have temporarily rejected the component request.</span></div></td></tr>`;
}

function currentPracticePrice(symbol, exchange, fallback) {
  return practicePrices.find(item => item.symbol === symbol && item.exchange === exchange)?.price || fallback;
}

function holdingTime(startedAt, endedAt = new Date().toISOString()) {
  const minutes = Math.max(0, Math.floor((new Date(endedAt) - new Date(startedAt)) / 60000));
  const days = Math.floor(minutes / 1440), hours = Math.floor((minutes % 1440) / 60), mins = minutes % 60;
  return `${days ? `${days}d ` : ""}${hours}h ${mins}m`;
}

function savePracticeTrades() {
  localStorage.setItem(practicePositionsKey, JSON.stringify(practicePositions));
  localStorage.setItem(practiceHistoryKey, JSON.stringify(practiceHistory));
}

function renderPracticePortfolio() {
  let totalInvested = 0, totalValue = 0;
  $("practicePositions").innerHTML = practicePositions.length ? practicePositions.map(position => {
    const price = currentPracticePrice(position.symbol, position.exchange, position.entryPrice);
    const value = position.quantity * price;
    const profit = value - position.invested;
    totalInvested += position.invested; totalValue += value;
    return `<article class="practice-row"><div><strong>${escapeHtml(position.company)}</strong><small>${escapeHtml(position.symbol)} · bought ${new Date(position.boughtAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</small></div><div><small>Holding</small><strong>${holdingTime(position.boughtAt)}</strong></div><div><small>Shares</small><strong>${position.quantity}</strong></div><div><small>Entry</small><strong>₹${position.entryPrice.toLocaleString("en-IN")}</strong></div><div><small>Latest</small><strong>₹${price.toLocaleString("en-IN")}</strong></div><div><small>Unrealized P/L</small><strong class="${profit >= 0 ? "profit" : "loss"}">${profit >= 0 ? "+" : ""}₹${profit.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></div><button class="button ghost" data-sell-position="${position.id}">Sell</button></article>`;
  }).join("") : `<div class="empty-state"><strong>No open practice positions</strong><span>Open a stock chart and click Buy for practice.</span></div>`;
  const unrealized = totalValue - totalInvested;
  $("practicePortfolioSummary").textContent = `${practicePositions.length} open · invested ₹${totalInvested.toLocaleString("en-IN", { maximumFractionDigits: 0 })} · unrealized ${unrealized >= 0 ? "+" : ""}₹${unrealized.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  $("practiceHistory").innerHTML = practiceHistory.length ? practiceHistory.slice().reverse().map(trade => `<article class="practice-row"><div><strong>${escapeHtml(trade.company)}</strong><small>${escapeHtml(trade.symbol)} · ${holdingTime(trade.boughtAt, trade.soldAt)}</small></div><div><small>Shares</small><strong>${trade.quantity}</strong></div><div><small>Entry</small><strong>₹${trade.entryPrice.toLocaleString("en-IN")}</strong></div><div><small>Exit</small><strong>₹${trade.exitPrice.toLocaleString("en-IN")}</strong></div><div><small>Sold</small><strong>${new Date(trade.soldAt).toLocaleDateString("en-IN")}</strong></div><div><small>Realized P/L</small><strong class="${trade.profit >= 0 ? "profit" : "loss"}">${trade.profit >= 0 ? "+" : ""}₹${trade.profit.toLocaleString("en-IN", { maximumFractionDigits: 2 })} (${trade.returnPercent.toFixed(2)}%)</strong></div><span></span></article>`).join("") : `<div class="empty-state"><strong>No completed practice trades</strong><span>Sell an open position to record realized profit or loss.</span></div>`;
}

function buyPracticePosition() {
  if (!activeAnalysis) return;
  const investment = Number($("paperInvestment").value);
  const entryPrice = Number($("paperEntry").value);
  const quantity = Math.floor(investment / entryPrice);
  if (!(investment > 0 && entryPrice > 0 && quantity > 0)) return toast("Enter enough investment for at least one share");
  practicePositions.push({ id: `${Date.now()}-${activeAnalysis.symbol}`, company: activeAnalysis.company, symbol: activeAnalysis.symbol, exchange: activeAnalysis.exchange, quantity, entryPrice, invested: quantity * entryPrice, boughtAt: new Date().toISOString() });
  savePracticeTrades(); renderPracticePortfolio(); $("stockChartDialog").close(); toast(`Practice buy recorded: ${quantity} ${activeAnalysis.symbol}`);
}

function sellPracticePosition(id) {
  const index = practicePositions.findIndex(position => position.id === id);
  if (index < 0) return;
  const position = practicePositions[index];
  const exitPrice = currentPracticePrice(position.symbol, position.exchange, position.entryPrice);
  const profit = position.quantity * exitPrice - position.invested;
  practiceHistory.push({ ...position, exitPrice, soldAt: new Date().toISOString(), profit, returnPercent: position.invested ? profit / position.invested * 100 : 0 });
  practicePositions.splice(index, 1);
  savePracticeTrades(); renderPracticePortfolio(); toast(`Practice sale recorded: ${profit >= 0 ? "profit" : "loss"} ₹${Math.abs(profit).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`);
}

function renderPriceChart(item) {
  const points = item.chart || [];
  if (points.length < 2) {
    $("stockPriceChart").innerHTML = `<text x="450" y="150" text-anchor="middle" class="chart-label">Chart data unavailable. Run the stock analysis job.</text>`;
    return;
  }
  const width = 900, height = 300, padX = 48, padY = 28;
  const prices = points.map(point => Number(point.close));
  const min = Math.min(...prices), max = Math.max(...prices), range = max - min || 1;
  const coords = points.map((point, index) => ({
    x: padX + index / (points.length - 1) * (width - padX * 2),
    y: padY + (max - Number(point.close)) / range * (height - padY * 2)
  }));
  const line = coords.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L ${coords.at(-1).x.toFixed(1)} ${height - padY} L ${coords[0].x.toFixed(1)} ${height - padY} Z`;
  const grids = [0, 1, 2, 3, 4].map(index => {
    const y = padY + index / 4 * (height - padY * 2);
    const price = max - index / 4 * range;
    return `<line class="chart-grid" x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}"/><text class="chart-label" x="5" y="${y + 3}">₹${price.toFixed(0)}</text>`;
  }).join("");
  $("stockPriceChart").innerHTML = `${grids}<path class="chart-area" d="${area}"/><path class="chart-line" d="${line}"/><text class="chart-label" x="${padX}" y="${height - 7}">${escapeHtml(points[0].date)}</text><text class="chart-label" text-anchor="end" x="${width - padX}" y="${height - 7}">${escapeHtml(points.at(-1).date)}</text>`;
}

function calculatePaperTrade() {
  const investment = Number($("paperInvestment").value);
  const entry = Number($("paperEntry").value);
  const exit = Number($("paperExit").value);
  if (!(investment > 0 && entry > 0 && exit > 0)) {
    $("paperTradeResults").innerHTML = `<div class="empty-state"><strong>Enter valid positive values</strong><span>Investment, entry, and exit prices are required.</span></div>`;
    return;
  }
  const quantity = Math.floor(investment / entry);
  const invested = quantity * entry;
  const unused = investment - invested;
  const exitValue = quantity * exit;
  const profit = exitValue - invested;
  const returnPercent = invested ? profit / invested * 100 : 0;
  const direction = profit >= 0 ? "profit" : "loss";
  $("paperTradeResults").innerHTML = `
    <article class="paper-result"><small>Whole shares</small><strong>${quantity.toLocaleString("en-IN")}</strong></article>
    <article class="paper-result"><small>Amount invested</small><strong>₹${invested.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></article>
    <article class="paper-result"><small>Unused cash</small><strong>₹${unused.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></article>
    <article class="paper-result"><small>Exit value</small><strong>₹${exitValue.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></article>
    <article class="paper-result"><small>Profit / loss</small><strong class="${direction}">${profit >= 0 ? "+" : ""}₹${profit.toLocaleString("en-IN", { maximumFractionDigits: 2 })} (${returnPercent.toFixed(2)}%)</strong></article>`;
}

function openStockChart(item) {
  activeAnalysis = item;
  $("stockChartName").textContent = item.company;
  $("stockChartMeta").textContent = `${item.symbol} · ${item.exchange} · ${item.signal} · as of ${item.asOf}`;
  $("paperEntry").value = currentPracticePrice(item.symbol, item.exchange, item.close);
  $("paperExit").value = item.signal === "Bullish" ? item.resistance20d : item.signal === "Bearish" ? item.support20d : item.close;
  const suffix = item.exchange === "NSE" ? ".NS" : ".BO";
  $("yahooChartLink").href = `https://finance.yahoo.com/quote/${encodeURIComponent(item.symbol + suffix)}/chart/`;
  $("nseChartLink").href = item.exchange === "NSE" ? `https://www.nseindia.com/get-quotes/equity?symbol=${encodeURIComponent(item.symbol)}` : `https://www.bseindia.com/stock-share-price/x/${encodeURIComponent(item.symbol)}/`;
  $("nseChartLink").textContent = `${item.exchange} chart`;
  renderPriceChart(item);
  calculatePaperTrade();
  $("stockChartDialog").showModal();
}

function formatAmount(value, currency = "INR") {
  const number = Number(value);
  if (!value || Number.isNaN(number)) return "Not available";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency === "INR" ? "INR" : currency, maximumFractionDigits: 2 }).format(number);
}

function comparison(current, previous) {
  const now = Number(current), before = Number(previous);
  if (!current || !previous || Number.isNaN(now) || Number.isNaN(before) || before === 0) return { text: "Previous comparison unavailable", className: "" };
  const percent = ((now - before) / Math.abs(before)) * 100;
  return { text: `${percent >= 0 ? "+" : ""}${percent.toFixed(1)}% vs previous quarter`, className: percent >= 0 ? "positive" : "negative" };
}

function openCompanyDetail(symbol, exchange) {
  const company = results.find(item => item.symbol === symbol && item.exchange === exchange) || newsItems.find(item => item.symbol === symbol && item.exchange === exchange);
  if (!company) return;
  const financial = financialItems.find(item => item.symbol === symbol && item.exchange === exchange);
  const related = newsItems.filter(item => item.symbol === symbol && item.exchange === exchange).slice(0, 25);
  $("companyDetailName").textContent = company.company;
  $("companyDetailSymbol").textContent = `${symbol} · ${exchange}`;
  $("financialPeriod").textContent = financial ? `${financial.quarter} · period ended ${formatDate(financial.periodEnded)}` : "Latest available filing";
  if (financial) {
    const revenueComparison = comparison(financial.revenue, financial.previousRevenue);
    const profitComparison = comparison(financial.profitLoss, financial.previousProfitLoss);
    const filingUrl = safeUrl(financial.sourceUrl);
    $("financialCards").innerHTML = `
      <article class="financial-card"><small>Revenue / total income</small><strong>${escapeHtml(formatAmount(financial.revenue, financial.currency))}</strong><span class="${revenueComparison.className}">${revenueComparison.text}</span></article>
      <article class="financial-card"><small>Profit or loss</small><strong class="${Number(financial.profitLoss) < 0 ? "negative" : ""}">${escapeHtml(formatAmount(financial.profitLoss, financial.currency))}</strong><span class="${profitComparison.className}">${profitComparison.text}</span></article>
      <article class="financial-card"><small>Previous-quarter profit/loss</small><strong class="${Number(financial.previousProfitLoss) < 0 ? "negative" : ""}">${escapeHtml(formatAmount(financial.previousProfitLoss, financial.currency))}</strong><span>${filingUrl ? `<a class="news-link" href="${escapeHtml(filingUrl)}" target="_blank" rel="noopener">Open NSE filing</a>` : escapeHtml(financial.currency || "INR")}</span></article>`;
    $("financialNotice").textContent = financial.profitLoss ? "Values are shown in the unit supplied by the source feed." : "The exchange filing metadata is available, but numeric profit/loss fields were not supplied. Connect a financial-data fallback feed for amounts.";
  } else {
    $("financialCards").innerHTML = `<article class="financial-card"><small>Financial summary</small><strong>Not available</strong><span>Run the financials job or connect a fallback feed.</span></article>`;
    $("financialNotice").textContent = "No previous-quarter financial summary was found for this company.";
  }
  $("relatedNewsSummary").textContent = `${related.length} recent item${related.length === 1 ? "" : "s"}`;
  $("relatedNewsList").innerHTML = related.length ? related.map(item => {
    const url = safeUrl(item.url);
    return `<article class="related-news-item"><div><h4>${escapeHtml(item.headline)}</h4><p>${escapeHtml(item.type)} · ${new Date(item.publishedAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p></div>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Open source</a>` : ""}</article>`;
  }).join("") : `<div class="empty-state"><strong>No related news or events</strong><span>Run the news job to refresh this company.</span></div>`;
  $("companyDialog").showModal();
}

function classifyNews(item) {
  const text = `${item.headline} ${item.summary}`.toLowerCase();
  if (item.type.toLowerCase().includes("upcoming")) return "event";
  if (/(order|contract|work order|letter of award|purchase order|tender|project awarded)/.test(text)) return "contract";
  if (/(financial results|quarterly results|audited results|unaudited results)/.test(text)) return "result";
  if (/(default|fraud|penalty|fine|litigation|insolvency|bankruptcy|delisting|resignation|warning|show cause|adverse|downgrade)/.test(text)) return "risk";
  if (/(dividend|bonus|buyback|approval|award|patent|launch|commissioned|expansion|acquisition|partnership|rating upgrade)/.test(text)) return "positive";
  return "neutral";
}

function eventRecencyWeight(value) {
  const days = Math.max(0, (Date.now() - new Date(value).getTime()) / 86400000);
  return days <= 30 ? 1 : days <= 90 ? 0.7 : 0.4;
}

function eventSuggestion() {
  if (!activeCompany) return null;
  const weights = { contract: 3, positive: 2, risk: -4, result: 0, event: 0, neutral: 0 };
  const exchangeEvents = newsItems
    .filter(item => item.symbol === activeCompany.symbol && item.exchange === activeCompany.exchange)
    .map(item => ({ title: item.headline, category: classifyNews(item), publishedAt: item.publishedAt, source: "Exchange filing" }));
  const analyzedEvents = companyNewsAnalysis?.symbol === activeCompany.symbol ? companyNewsAnalysis.stories.map(item => ({
    title: item.title, category: item.category, publishedAt: item.publishedAt, source: item.source,
    sentimentScore: Number(item.sentimentScore) || 0
  })) : [];
  const uniqueEvents = [...new Map([...exchangeEvents, ...analyzedEvents].map(item => [item.title.toLowerCase().replace(/\W+/g, " ").trim(), item])).values()];
  const events = uniqueEvents.map(item => {
    const score = (weights[item.category] || 0) * eventRecencyWeight(item.publishedAt) + Math.max(-1, Math.min(1, item.sentimentScore || 0));
    return { ...item, score };
  });
  const financial = financialItems.find(item => item.symbol === activeCompany.symbol && item.exchange === activeCompany.exchange);
  let financialScore = 0;
  if (financial?.profitLoss !== undefined && financial?.previousProfitLoss !== undefined) {
    const current = Number(financial.profitLoss), previous = Number(financial.previousProfitLoss);
    if (Number.isFinite(current) && Number.isFinite(previous)) financialScore = current > previous ? 3 : current < previous ? -3 : 0;
  }
  const positive = events.filter(item => item.score > 0).sort((a, b) => b.score - a.score);
  const negative = events.filter(item => item.score < 0).sort((a, b) => a.score - b.score);
  const positiveScore = positive.slice(0, 10).reduce((sum, item) => sum + item.score, 0) + Math.max(0, financialScore);
  const negativeScore = Math.abs(negative.slice(0, 10).reduce((sum, item) => sum + item.score, 0) + Math.min(0, financialScore));
  const netScore = Math.round((positiveScore - negativeScore) * 10) / 10;
  const signal = netScore >= 6 ? "buy" : netScore <= -6 ? "sell" : "hold";
  const label = signal === "buy" ? "Positive / Buy-watch" : signal === "sell" ? "Negative / Sell-review" : "Hold / Monitor";
  const confidence = Math.min(95, Math.round(45 + Math.min(50, Math.abs(netScore) * 2)));
  return { signal, label, confidence, netScore, positiveScore: Math.round(positiveScore * 10) / 10, negativeScore: Math.round(negativeScore * 10) / 10, positive, negative, financialScore };
}

function renderEventSuggestion() {
  const suggestion = eventSuggestion();
  if (!suggestion) return;
  $("eventSuggestionSummary").textContent = `${suggestion.label} based on recent company events`;
  $("eventSuggestionScore").innerHTML = `
    <article class="suggestion-card ${suggestion.signal}"><small>Current suggestion</small><strong>${suggestion.label}</strong><span>Heuristic confidence ${suggestion.confidence}%</span></article>
    <article class="suggestion-card"><small>Net event score</small><strong>${suggestion.netScore > 0 ? "+" : ""}${suggestion.netScore}</strong><span>Buy-watch at +6, sell-review at -6</span></article>
    <article class="suggestion-card buy"><small>Positive event points</small><strong>+${suggestion.positiveScore}</strong><span>${suggestion.positive.length} positive drivers</span></article>
    <article class="suggestion-card sell"><small>Negative event points</small><strong>-${suggestion.negativeScore}</strong><span>${suggestion.negative.length} negative drivers</span></article>`;
  const evidence = (items, empty) => items.slice(0, 5).map(item => `<div class="evidence-item"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.category)} · ${new Date(item.publishedAt).toLocaleDateString("en-IN", { dateStyle: "medium" })} · ${escapeHtml(item.source)}</small></div>`).join("") || `<div class="evidence-item"><small>${empty}</small></div>`;
  $("eventSuggestionEvidence").innerHTML = `
    <section class="evidence-column"><h3>Positive buy-watch events</h3>${evidence(suggestion.positive, "No positive event drivers found.")}</section>
    <section class="evidence-column"><h3>Negative sell-review events</h3>${evidence(suggestion.negative, "No negative event drivers found.")}</section>`;
}

function renderCompanyPage() {
  if (!activeCompany) return;
  const { symbol, exchange, company } = activeCompany;
  const financial = financialItems.find(item => item.symbol === symbol && item.exchange === exchange);
  const upcoming = results.filter(item => item.symbol === symbol && item.exchange === exchange);
  const related = newsItems.filter(item => item.symbol === symbol && item.exchange === exchange);
  const categorized = related.map(item => ({ ...item, category: classifyNews(item) }));
  const counts = Object.fromEntries(["contract", "positive", "risk", "result", "event", "neutral"].map(category => [category, categorized.filter(item => item.category === category).length]));
  $("companyPageLogo").textContent = initials(company);
  $("companyPageName").textContent = company;
  $("companyPageMeta").textContent = `${symbol} · ${exchange} · ${related.length} recent filings`;
  $("companyWatchButton").textContent = isWatched(activeCompany) ? "Remove from watchlist" : "Add to watchlist";
  $("companyExchangeLink").href = exchange === "NSE" ? `https://www.nseindia.com/get-quotes/equity?symbol=${encodeURIComponent(symbol)}` : `https://www.bseindia.com/stock-share-price/x/${encodeURIComponent(symbol)}/`;
  $("companyExchangeLink").textContent = `Open ${exchange} quote`;
  const price = activeStockProfile?.priceInfo;
  const metadata = activeStockProfile?.metadata;
  const industry = activeStockProfile?.industryInfo;
  const valuation = companyFundamentals?.valuation || {};
  const priceHistory = companyFundamentals?.priceHistory || [];
  const latestHistory = priceHistory.at(-1);
  const previousHistory = priceHistory.at(-2);
  const fallbackChange = latestHistory && previousHistory ? (Number(latestHistory.close) / Number(previousHistory.close) - 1) * 100 : null;
  const yearHistory = priceHistory.slice(-54);
  const yearPrices = yearHistory.map(item => Number(item.close)).filter(Number.isFinite);
  const fallbackRange = yearPrices.length ? { min: Math.min(...yearPrices), max: Math.max(...yearPrices) } : null;
  const currentPrice = price?.lastPrice ?? valuation.lastPrice ?? latestHistory?.close;
  const dayChange = price?.pChange ?? fallbackChange;
  const weekRange = price?.weekHighLow ?? fallbackRange;
  const latestQuarter = financial?.quarter || companyFundamentals?.quarterlyHistory?.at(-1)?.quarter;
  $("companyStats").innerHTML = `
    <article class="company-stat"><small>Current price</small><strong>${currentPrice ? `₹${Number(currentPrice).toLocaleString("en-IN")}` : "Update required"}</strong><span>${price?.lastPrice ? "NSE quote" : valuation.priceSource || "No price source available"}</span></article>
    <article class="company-stat"><small>Day change</small><strong class="${Number(dayChange) < 0 ? "negative" : "positive"}">${dayChange !== null && dayChange !== undefined ? `${Number(dayChange).toFixed(2)}%` : "Update required"}</strong><span>${price?.pChange !== undefined ? "NSE intraday" : "Fallback: latest sampled closes"}</span></article>
    <article class="company-stat"><small>52-week range</small><strong>${weekRange ? `₹${Number(weekRange.min).toLocaleString("en-IN")} – ₹${Number(weekRange.max).toLocaleString("en-IN")}` : "Update required"}</strong><span>${price?.weekHighLow ? "NSE 52-week range" : "Fallback: five-year chart data"}</span></article>
    <article class="company-stat"><small>Industry</small><strong>${escapeHtml(industry?.industry || metadata?.industry || "Not available")}</strong></article>
    <article class="company-stat"><small>Next result date</small><strong>${upcoming[0] ? formatDate(upcoming[0].date) : "Not announced"}</strong></article>
    <article class="company-stat"><small>Latest filed quarter</small><strong>${latestQuarter ? escapeHtml(latestQuarter) : "Update required"}</strong></article>
    <article class="company-stat"><small>Contracts / orders</small><strong>${counts.contract}</strong></article>
    <article class="company-stat"><small>Potential risk filings</small><strong>${counts.risk}</strong></article>`;
  if (financial) {
    const filing = safeUrl(financial.sourceUrl);
    $("companyFinancials").innerHTML = `<div class="financial-cards">
      <article class="financial-card"><small>Period ended</small><strong>${formatDate(financial.periodEnded)}</strong><span>${escapeHtml(financial.quarter)}</span></article>
      <article class="financial-card"><small>Revenue / total income</small><strong>${escapeHtml(formatAmount(financial.revenue, financial.currency))}</strong><span>${comparison(financial.revenue, financial.previousRevenue).text}</span></article>
      <article class="financial-card"><small>Profit or loss</small><strong>${escapeHtml(formatAmount(financial.profitLoss, financial.currency))}</strong><span>${filing ? `<a class="news-link" href="${escapeHtml(filing)}" target="_blank" rel="noopener">Open exchange filing</a>` : "Numeric data unavailable"}</span></article>
    </div>`;
  } else $("companyFinancials").innerHTML = `<div class="empty-state"><strong>No quarterly filing found</strong><span>Run the financials job to refresh exchange filings.</span></div>`;
  $("companySignals").innerHTML = [
    ["contract", "Contracts & orders"], ["positive", "Potential positive"], ["risk", "Potential risk"],
    ["result", "Result filings"], ["event", "Upcoming events"], ["neutral", "Other filings"]
  ].map(([category, label]) => `<div class="signal-row"><span class="signal-tag ${category}">${label}</span><strong>${counts[category]}</strong></div>`).join("");
  renderCompanyTimeline(categorized);
  renderCompanyAnalyzer();
  renderEventSuggestion();
  renderCompanyFundamentals();
  renderCompanyDataStatus();
  renderCompanyPriceHistory();
}

function renderCompanyDataStatus() {
  if (!activeCompany) return;
  const history = companyFundamentals?.priceHistory || [];
  const checks = [
    activeStockProfile?.priceInfo?.lastPrice || companyFundamentals?.valuation?.lastPrice,
    activeStockProfile?.industryInfo?.industry || activeStockProfile?.metadata?.industry,
    companyFundamentals?.valuation?.marketCapCrore,
    companyFundamentals?.shareholding?.length,
    companyFundamentals?.quarterlyHistory?.length,
    history.length,
    companyNewsAnalysis?.storyCount,
    financialItems.some(item => item.symbol === activeCompany.symbol && item.exchange === activeCompany.exchange),
  ];
  const available = checks.filter(Boolean).length;
  $("companyDataCoverage").textContent = `${available} of ${checks.length} company datasets available`;
  const updatedAt = companyFundamentals?.updatedAt ? new Date(companyFundamentals.updatedAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "not yet";
  $("companyDataUpdated").textContent = available === checks.length ? `All tracked datasets available · updated ${updatedAt}` : `${checks.length - available} datasets need another source or refresh · fundamentals updated ${updatedAt}`;
  $("companyDataRetryButton").hidden = available === checks.length;
}

function renderCompanyPriceHistory() {
  if (!activeCompany) return;
  document.querySelectorAll("[data-chart-range]").forEach(button => button.classList.toggle("active", button.dataset.chartRange === companyChartRange));
  const daily = companyFundamentals?.priceHistory || [];
  const intraday = companyFundamentals?.intradayHistory || [];
  const now = new Date();
  const cutoff = new Date(now);
  const rangeMonths = { "1M": 1, "3M": 3, "1Y": 12, "3Y": 36, "5Y": 60 };
  if (rangeMonths[companyChartRange]) cutoff.setMonth(cutoff.getMonth() - rangeMonths[companyChartRange]);
  let points;
  if (companyChartRange === "1D") {
    const lastDay = intraday.at(-1)?.timestamp?.slice(0, 10);
    points = intraday.filter(item => item.timestamp.startsWith(lastDay || ""));
  } else if (companyChartRange === "1W") {
    points = intraday;
  } else {
    points = daily.filter(item => new Date(item.date) >= cutoff);
  }
  const chart = $("companyPriceHistoryChart");
  if (points.length < 2) {
    $("companyPriceHistorySummary").textContent = `${companyChartRange} history unavailable. Use Refresh chart.`;
    $("companyChartMeta").textContent = "No cached price history";
    chart.innerHTML = `<text x="550" y="210" text-anchor="middle" class="chart-label">${companyChartRange} chart data unavailable. Click Refresh chart.</text>`;
    return;
  }
  const width = 1100, height = 420, padX = 72, padY = 38;
  const prices = points.map(point => Number(point.close));
  const min = Math.min(...prices), max = Math.max(...prices), range = max - min || 1;
  const coords = points.map((point, index) => ({ x: padX + index / (points.length - 1) * (width - padX * 2), y: padY + (max - Number(point.close)) / range * (height - padY * 2) }));
  const line = coords.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L ${coords.at(-1).x.toFixed(1)} ${height - padY} L ${coords[0].x.toFixed(1)} ${height - padY} Z`;
  const grids = [0, 1, 2, 3, 4].map(index => {
    const y = padY + index / 4 * (height - padY * 2);
    const priceValue = max - index / 4 * range;
    return `<line class="chart-grid" x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}"/><text class="chart-label" x="8" y="${y + 3}">₹${priceValue.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</text>`;
  }).join("");
  const labelFor = point => {
    const value = point.timestamp || point.date;
    return new Date(value).toLocaleString("en-IN", companyChartRange === "1D" || companyChartRange === "1W" ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" } : { month: "short", year: "numeric" });
  };
  chart.innerHTML = `<defs><linearGradient id="companyChartGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#62bad7" stop-opacity=".9"/><stop offset="100%" stop-color="#d8f5f5" stop-opacity=".25"/></linearGradient></defs>${grids}<path class="chart-area" d="${area}"/><path class="chart-line" d="${line}"/><circle class="chart-last-point" cx="${coords.at(-1).x}" cy="${coords.at(-1).y}" r="5"></circle><text class="chart-label" x="${padX}" y="${height - 8}">${escapeHtml(labelFor(points[0]))}</text><text class="chart-label" text-anchor="end" x="${width - padX}" y="${height - 8}">${escapeHtml(labelFor(points.at(-1)))}</text>`;
  const change = (prices.at(-1) / prices[0] - 1) * 100;
  $("companyPriceHistorySummary").textContent = `${companyChartRange} · ${points.length} prices · ${companyFundamentals.priceHistorySource || "delayed market data"}`;
  $("companyChartMeta").innerHTML = `<span>Open ₹${prices[0].toLocaleString("en-IN")}</span><span>Latest ₹${prices.at(-1).toLocaleString("en-IN")}</span><span>Low ₹${min.toLocaleString("en-IN")}</span><span>High ₹${max.toLocaleString("en-IN")}</span><strong class="${change >= 0 ? "positive" : "negative"}">${change >= 0 ? "+" : ""}${change.toFixed(2)}%</strong>`;
}

function formatCrore(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const amount = Number(value);
  return Number.isFinite(amount) ? `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr` : "Unavailable";
}

function renderProfitHistoryChart(history) {
  const chart = $("profitHistoryChart");
  if (!history.length) {
    chart.innerHTML = `<text x="450" y="150" text-anchor="middle" class="profit-label">No parsed quarterly profit/loss values available</text>`;
    return;
  }
  const values = history.map(item => Number(item.profitLossCrore));
  const max = Math.max(...values.map(Math.abs), 1);
  const zeroY = 145;
  const scale = 105 / max;
  const width = 780 / history.length;
  chart.innerHTML = `
    <line x1="70" y1="${zeroY}" x2="860" y2="${zeroY}" class="profit-zero"></line>
    <line x1="70" y1="40" x2="860" y2="40" class="profit-grid"></line>
    <line x1="70" y1="250" x2="860" y2="250" class="profit-grid"></line>
    ${history.map((item, index) => {
      const value = Number(item.profitLossCrore);
      const height = Math.abs(value) * scale;
      const x = 82 + index * width;
      const y = value >= 0 ? zeroY - height : zeroY;
      const label = new Date(item.periodEnded).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
      return `<rect x="${x}" y="${y}" width="${Math.max(16, width - 18)}" height="${height}" rx="4" class="profit-bar ${value >= 0 ? "positive" : "negative"}"><title>${label}: ${formatCrore(value)}</title></rect><text x="${x + Math.max(16, width - 18) / 2}" y="${value >= 0 ? Math.max(28, y - 7) : Math.min(270, y + height + 13)}" text-anchor="middle" class="profit-value">${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text><text x="${x + Math.max(16, width - 18) / 2}" y="288" text-anchor="middle" class="profit-label">${label}</text>`;
    }).join("")}
    <text x="12" y="22" class="profit-label">Profit / loss (₹ crore)</text>`;
}

function renderCompanyFundamentals() {
  if (!companyFundamentals || !activeCompany || companyFundamentals.symbol !== activeCompany.symbol) {
    $("companyValuationSummary").textContent = "Loading valuation, ownership, and quarterly history";
    $("companyValuation").innerHTML = `<div class="empty-state"><strong>Loading company value</strong><span>Uncached companies can take up to 20 seconds.</span></div>`;
    $("companyOwnership").innerHTML = `<div class="empty-state"><strong>Loading ownership</strong><span>Fetching NSE shareholding filings.</span></div>`;
    $("profitHistorySummary").textContent = "Loading official quarterly filings";
    renderProfitHistoryChart([]);
    return;
  }
  const valuation = companyFundamentals.valuation || {};
  const sourceErrors = companyFundamentals.errors || [];
  const friendlyErrors = sourceErrors.map(error => error.includes("HTTP Error 403") ? "NSE quote temporarily blocked; fallback or last-known-good data retained." : error);
  $("companyValuationSummary").textContent = valuation.marketCapCrore ? "Estimated equity market value from available price and issued shares" : sourceErrors.length ? "Some sources are unavailable; showing partial fundamentals" : "Market value unavailable from the current exchange response";
  $("companyValuation").innerHTML = `
    <article class="fundamental-card"><small>Market capitalization</small><strong>${formatCrore(valuation.marketCapCrore)}</strong><span>Last price × issued shares</span></article>
    <article class="fundamental-card"><small>Last traded price</small><strong>${valuation.lastPrice ? `₹${Number(valuation.lastPrice).toLocaleString("en-IN")}` : "Unavailable"}</strong><span>${escapeHtml(valuation.priceSource || "NSE quote")}</span></article>
    <article class="fundamental-card"><small>Issued shares</small><strong>${valuation.issuedShares ? Number(valuation.issuedShares).toLocaleString("en-IN") : "Unavailable"}</strong><span>Equity shares</span></article>
    <article class="fundamental-card"><small>Enterprise value</small><strong>Unavailable</strong><span>Requires reliable debt and cash data</span></article>
    ${friendlyErrors.length ? `<div class="coverage-warning">Partial data: ${escapeHtml(friendlyErrors.slice(0, 2).join(" · "))}</div>` : ""}`;
  const ownership = companyFundamentals.shareholding || [];
  $("companyOwnershipSummary").textContent = ownership.length ? `${ownership.length} recent NSE shareholding periods` : "No NSE shareholding pattern available";
  const majorInvestors = ownership[0]?.majorInvestors || [];
  const investorList = majorInvestors.length ? `<div class="major-investors"><h3>Named major investors</h3>${majorInvestors.map(item => `<div class="major-investor"><span>${escapeHtml(item.name)}</span><strong>${Number(item.percent).toFixed(2)}%</strong></div>`).join("")}</div>` : "";
  $("companyOwnership").innerHTML = ownership.length ? investorList + ownership.map(item => {
    const filing = safeUrl(item.detailedFilingUrl);
    return `<section class="ownership-period"><div class="ownership-period-heading"><strong>${formatDate(item.asOnDate)}</strong>${filing ? `<a href="${escapeHtml(filing)}" target="_blank" rel="noopener">Detailed investors filing</a>` : ""}</div><div class="ownership-bar-label"><span>Promoter & promoter group</span><strong>${Number(item.promoterPercent || 0).toFixed(2)}%</strong></div><div class="ownership-bar"><span style="width:${Number(item.promoterPercent || 0)}%"></span></div><div class="ownership-bar-label"><span>Public investors</span><strong>${Number(item.publicPercent || 0).toFixed(2)}%</strong></div><div class="ownership-bar public"><span style="width:${Number(item.publicPercent || 0)}%"></span></div></section>`;
  }).join("") : `<div class="empty-state"><strong>Ownership unavailable</strong><span>Run refresh when NSE shareholding data is available.</span></div>`;
  const history = companyFundamentals.quarterlyHistory || [];
  $("profitHistorySummary").textContent = history.length ? `${history.length} parsed quarterly NSE filings · values in INR crore` : "No quarterly XBRL profit/loss values were parsed";
  renderProfitHistoryChart(history);
}

async function loadCompanyFundamentals(refresh = false) {
  if (!activeCompany || location.protocol === "file:") return;
  const requestId = ++companyFundamentalsRequest;
  const requestedKey = companyKey(activeCompany.exchange, activeCompany.symbol);
  companyFundamentals = null;
  renderCompanyFundamentals();
  try {
    const params = new URLSearchParams({ company: activeCompany.company, symbol: activeCompany.symbol, exchange: activeCompany.exchange });
    if (refresh) params.set("refresh", "1");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    const response = await fetch(`/api/company-fundamentals?${params}`, { cache: "no-store", signal: controller.signal });
    clearTimeout(timeout);
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error("Fundamentals API unavailable. Restart scripts/job_server.py.");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Fundamentals unavailable");
    if (requestId !== companyFundamentalsRequest || !activeCompany || requestedKey !== companyKey(activeCompany.exchange, activeCompany.symbol)) return;
    companyFundamentals = payload;
    renderCompanyPage();
    if (refresh) toast("Company fundamentals refreshed");
  } catch (error) {
    if (requestId !== companyFundamentalsRequest || !activeCompany || requestedKey !== companyKey(activeCompany.exchange, activeCompany.symbol)) return;
    if (!refresh) {
      try {
        const cached = await fetch(`data/company-fundamentals/${encodeURIComponent(activeCompany.exchange)}-${encodeURIComponent(activeCompany.symbol)}.json`, { cache: "no-store" });
        if (cached.ok) {
          companyFundamentals = await cached.json();
          renderCompanyPage();
          return;
        }
      } catch {}
    }
    $("companyValuationSummary").textContent = "Company fundamentals unavailable";
    const message = error.name === "AbortError" ? "Request timed out after 30 seconds. Try Refresh fundamentals." : error.message;
    $("companyValuation").innerHTML = `<div class="empty-state"><strong>Fundamentals failed</strong><span>${escapeHtml(message)}</span></div>`;
    $("companyOwnership").innerHTML = `<div class="empty-state"><strong>Ownership unavailable</strong><span>${escapeHtml(message)}</span></div>`;
    $("profitHistorySummary").textContent = "Quarterly history unavailable";
    renderProfitHistoryChart([]);
  }
}

function renderCompanyAnalyzer() {
  if (!companyNewsAnalysis || !activeCompany || companyNewsAnalysis.symbol !== activeCompany.symbol) {
    $("companyAnalyzerSummary").textContent = "Loading six-month related news...";
    $("companyAnalyzerStats").innerHTML = "";
    $("companyAnalyzerStories").innerHTML = `<div class="empty-state"><strong>Analyzing related news</strong><span>Searching the previous six months.</span></div>`;
    return;
  }
  const filter = $("companyAnalyzerFilter").value;
  const stories = filter ? companyNewsAnalysis.stories.filter(item => item.category === filter) : companyNewsAnalysis.stories;
  const counts = companyNewsAnalysis.counts;
  $("companyAnalyzerSummary").textContent = `${companyNewsAnalysis.storyCount} related stories from the previous ${companyNewsAnalysis.periodMonths} months`;
  $("companyAnalyzerStats").innerHTML = [
    ["Total", companyNewsAnalysis.storyCount],
    ["Potential positive", counts.positive || 0],
    ["Potential risk", counts.risk || 0],
    ["Contracts", counts.contract || 0],
    ["Results", counts.result || 0]
  ].map(([label, value]) => `<article class="analyzer-stat"><small>${label}</small><strong>${value}</strong></article>`).join("");
  const warning = companyNewsAnalysis.storyCount < companyNewsAnalysis.minimumTarget
    ? `<div class="coverage-warning">Only ${companyNewsAnalysis.storyCount} credible stories were available. The analyzer does not fabricate stories to reach 10.</div>` : "";
  const list = stories.length ? stories.map(item => {
    const url = safeUrl(item.url);
    return `<article class="analyzer-story"><div><span class="signal-tag ${item.category}">${escapeHtml(item.category)}</span><small>${new Date(item.publishedAt).toLocaleDateString("en-IN", { dateStyle: "medium" })}</small></div><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || item.source)}</p><small>${escapeHtml(item.source)} · ${escapeHtml(item.sentiment)} sentiment</small></div>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Open source</a>` : ""}</article>`;
  }).join("") : `<div class="empty-state"><strong>No matching analyzed stories</strong><span>Try another category.</span></div>`;
  $("companyAnalyzerStories").innerHTML = warning + list;
  renderEventSuggestion();
}

async function loadCompanyNewsAnalysis(refresh = false) {
  if (!activeCompany || location.protocol === "file:") return;
  companyNewsAnalysis = null;
  renderCompanyAnalyzer();
  try {
    const params = new URLSearchParams({ company: activeCompany.company, symbol: activeCompany.symbol, exchange: activeCompany.exchange });
    if (refresh) params.set("refresh", "1");
    const response = await fetch(`/api/company-news?${params}`, { cache: "no-store" });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error("The analyzer API is unavailable. Start the app with python scripts/job_server.py.");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Company analyzer failed");
    companyNewsAnalysis = payload;
    renderCompanyAnalyzer();
    if (refresh) toast(`Analyzed ${payload.storyCount} related stories`);
  } catch (error) {
    if (!refresh) {
      try {
        const cached = await fetch(`data/company-news/${encodeURIComponent(activeCompany.exchange)}-${encodeURIComponent(activeCompany.symbol)}.json`, { cache: "no-store" });
        if (cached.ok) {
          companyNewsAnalysis = await cached.json();
          renderCompanyAnalyzer();
          return;
        }
      } catch {}
    }
    $("companyAnalyzerSummary").textContent = "Six-month news analysis unavailable";
    $("companyAnalyzerStats").innerHTML = "";
    $("companyAnalyzerStories").innerHTML = `<div class="empty-state"><strong>Analyzer server is not running</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

function renderCompanyTimeline(items) {
  const filter = $("companyNewsFilter").value;
  const filtered = filter ? items.filter(item => item.category === filter) : items;
  $("companyTimelineSummary").textContent = `${filtered.length} filing${filtered.length === 1 ? "" : "s"} shown`;
  $("companyTimeline").innerHTML = filtered.length ? filtered.map(item => {
    const url = safeUrl(item.url);
    return `<article class="timeline-item"><div><span class="signal-tag ${item.category}">${item.category}</span><p class="timeline-date">${new Date(item.publishedAt).toLocaleDateString("en-IN", { dateStyle: "medium" })}</p></div><div><h3>${escapeHtml(item.headline)}</h3><p>${escapeHtml(item.summary || item.type)}</p></div>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Open source</a>` : ""}</article>`;
  }).join("") : `<div class="empty-state"><strong>No matching filings</strong><span>Try another category or run the news job.</span></div>`;
}

function openCompanyPage(symbol, exchange, updateHistory = true) {
  activeCompany = companyIndex().find(item => item.symbol === symbol && item.exchange === exchange);
  if (!activeCompany) return;
  activeStockProfile = null;
  companyProfileStatus = "loading";
  companyNewsAnalysis = null;
  companyFundamentals = null;
  document.querySelectorAll(".dashboard-shell").forEach(element => element.hidden = true);
  $("companyPage").hidden = false;
  $("companySearchResults").hidden = true;
  if (updateHistory) history.replaceState(null, "", `#company=${encodeURIComponent(exchange)}:${encodeURIComponent(symbol)}`);
  renderCompanyPage();
  loadCompanyStockInfo();
  loadCompanyNewsAnalysis();
  loadCompanyFundamentals();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openCompanyFromHash() {
  const match = location.hash.match(/^#company=([^:]+):(.+)$/);
  if (!match) return false;
  const exchange = decodeURIComponent(match[1]).toUpperCase();
  const symbol = decodeURIComponent(match[2]).toUpperCase();
  const company = companyIndex().find(item => item.symbol === symbol && item.exchange === exchange);
  if (!company) return false;
  openCompanyPage(symbol, exchange, false);
  return true;
}

async function loadCompanyStockInfo() {
  activeStockProfile = null;
  companyProfileStatus = "loading";
  if (!activeCompany || activeCompany.exchange !== "NSE" || location.protocol === "file:") {
    companyProfileStatus = "unavailable";
    return;
  }
  try {
    const response = await fetch(`/api/company-profile?exchange=NSE&symbol=${encodeURIComponent(activeCompany.symbol)}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Profile unavailable");
    activeStockProfile = await response.json();
    companyProfileStatus = "available";
    renderCompanyPage();
  } catch {
    activeStockProfile = null;
    companyProfileStatus = "unavailable";
    renderCompanyPage();
  }
}

async function updateAllCompanyData() {
  if (!activeCompany) return;
  const buttons = [$("companyUpdateAllButton"), $("companyDataRetryButton")];
  buttons.forEach(button => { button.disabled = true; button.textContent = "Updating company data..."; });
  await Promise.allSettled([loadCompanyStockInfo(), loadCompanyFundamentals(true), loadCompanyNewsAnalysis(true)]);
  renderCompanyPage();
  buttons.forEach(button => { button.disabled = false; });
  $("companyUpdateAllButton").textContent = "Update all data";
  $("companyDataRetryButton").textContent = "Retry missing data";
  toast("Company data update completed");
}

function closeCompanyPage() {
  companyFundamentalsRequest++;
  activeCompany = null;
  activeStockProfile = null;
  companyProfileStatus = "idle";
  companyNewsAnalysis = null;
  companyFundamentals = null;
  $("companyPage").hidden = true;
  history.replaceState(null, "", location.pathname);
  setView("list");
}

function render() {
  renderMetrics();
  renderTable();
  renderCompanyDirectory();
  renderCalendar();
  renderNews();
  renderMarketNews();
  renderStockAnalysis();
  renderPracticePortfolio();
  renderWatchPredictions();
  renderMarketOverview();
  renderVerification();
}

function renderVerification() {
  const levels = verificationData.levels || {};
  const official = levels["official-exchange"] || results.filter(item => item.verificationLevel === "official-exchange").length;
  const external = levels["external-feed"] || results.filter(item => item.verificationLevel === "external-feed").length;
  const legacy = levels["legacy-unverified"] || results.filter(item => !item.verificationLevel || item.verificationLevel === "legacy-unverified").length;
  $("verificationRibbon").innerHTML = `
    <div><span class="quality-icon verified">✓</span><strong>${official}</strong><small>Official exchange verified</small></div>
    <div><span class="quality-icon external">↗</span><strong>${external}</strong><small>External-source records</small></div>
    <div><span class="quality-icon legacy">!</span><strong>${legacy}</strong><small>Legacy records to review</small></div>
    <div><span class="quality-icon policy">S</span><strong>Strict</strong><small>Fallbacks default to estimated</small></div>`;
  $("systemVerificationStatus").textContent = `${official} official result dates verified`;
  const jobs = verificationData.recentJobs || [];
  $("systemJobStatus").textContent = jobs.length ? `${jobs.filter(job => job.status === "success").length}/${jobs.length} recent jobs successful` : "No audited job runs yet";
  $("jobHealthGrid").innerHTML = `
    <article><small>Authentication</small><strong>Session protected</strong><span>SQLite users + HttpOnly cookie</span></article>
    <article><small>Result integrity</small><strong>${official} official</strong><span>${external + legacy} require source review</span></article>
    <article><small>Job audit trail</small><strong>${jobs.length} recent</strong><span>${jobs.filter(job => job.status === "failed").length} failed</span></article>
    <article><small>Database</small><strong>SQLite online</strong><span>Users, sessions, audits, verification</span></article>`;
}

function renderWatchPredictions() {
  const selected = $("watchPredictionFilter").value;
  const renderList = (items, target) => {
    const filtered = (items || []).filter(item => !selected || item.direction === selected);
    $(target).innerHTML = filtered.length ? filtered.map(item => {
      const tone = item.direction.startsWith("Positive") ? "positive" : item.direction.startsWith("Negative") ? "negative" : "neutral";
      const evidence = [...(item.catalysts || []), ...(item.risks || [])].slice(0, 3);
      return `<article class="watch-prediction-card" data-watch-symbol="${escapeHtml(item.symbol)}" data-watch-exchange="${escapeHtml(item.exchange)}">
        <div class="watch-card-heading"><div><h3>${escapeHtml(item.company)}</h3><p>${escapeHtml(item.exchange)}:${escapeHtml(item.symbol)}</p></div><span class="watch-direction ${tone}">${escapeHtml(item.direction)}</span></div>
        <div class="watch-score-row"><strong>${item.predictionScore > 0 ? "+" : ""}${escapeHtml(item.predictionScore)}</strong><span>${escapeHtml(item.confidence)}% confidence</span><span>${escapeHtml(item.riskLevel)} risk</span></div>
        <p class="watch-reason">${escapeHtml(item.reason)}</p>
        <div class="watch-facts"><span>${escapeHtml(item.technicalSignal)} technical</span><span>${escapeHtml(item.confirmedNewsCount)} verified</span><span class="${item.gossipCount ? "unverified" : ""}">${escapeHtml(item.gossipCount)} unverified</span></div>
        <div class="watch-evidence">${evidence.map(row => `<span>${row.verified ? "Verified" : "Unverified"}: ${escapeHtml(row.label)}</span>`).join("")}</div>
      </article>`;
    }).join("") : `<div class="empty-state"><strong>No matching stocks</strong><span>Run the prediction job after refreshing market news and stock analysis.</span></div>`;
  };
  renderList(watchPredictionData.today, "todayWatchList");
  renderList(watchPredictionData.tomorrow, "tomorrowWatchList");
  const count = (watchPredictionData.today || []).length + (watchPredictionData.tomorrow || []).length;
  $("watchPredictionSummary").textContent = `${count} ranked watches. Unverified chatter is labeled and downweighted.`;
  if (watchPredictionData.method) $("watchPredictionMethod").textContent = `${watchPredictionData.method} ${watchPredictionData.disclaimer || ""}`;
}

function setView(next) {
  view = next;
  $("companyPage").hidden = true;
  document.querySelectorAll(".dashboard-shell").forEach(element => element.hidden = false);
  document.querySelectorAll(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === next));
  $("dashboardView").hidden = next !== "dashboard";
  $("listView").hidden = next === "dashboard" || next === "calendar" || next === "companies" || next === "watchlist" || next === "stocks" || next === "markets" || next === "watch-today" || next === "news" || next === "learn" || next === "jobs";
  $("calendarView").hidden = next !== "calendar";
  $("companiesView").hidden = next !== "companies" && next !== "watchlist";
  $("stocksView").hidden = next !== "stocks";
  $("watchTodayView").hidden = next !== "watch-today";
  $("marketsView").hidden = next !== "markets";
  $("newsView").hidden = next !== "news";
  $("learnView").hidden = next !== "learn";
  $("jobsView").hidden = next !== "jobs";
  if (next === "jobs") refreshJobStatus();
  render();
}

function toast(message) {
  $("toast").textContent = message; $("toast").classList.add("show");
  setTimeout(() => $("toast").classList.remove("show"), 2600);
}

function formatRupees(value) {
  return `₹${Math.round(Number(value) || 0).toLocaleString("en-IN")}`;
}

function renderTaxEstimate() {
  const type = $("taxProfitType").value;
  const profit = Math.max(0, Number($("taxProfitAmount").value) || 0);
  const businessIncome = type === "intraday" || type === "fno" || type === "dividend";
  $("taxSlabLabel").hidden = !businessIncome;
  const slabRate = Number($("taxSlabRate").value) / 100;
  let taxable = profit, rate = slabRate, title = "Estimated slab-rate tax";
  if (type === "stcg") {
    rate = 0.20;
    title = "Estimated listed-equity STCG tax";
  } else if (type === "ltcg") {
    taxable = Math.max(0, profit - 125000);
    rate = 0.125;
    title = "Estimated listed-equity LTCG tax";
  }
  const baseTax = taxable * rate;
  const cess = baseTax * 0.04;
  const total = baseTax + cess;
  const notes = type === "ltcg" ? `The first ${formatRupees(Math.min(profit, 125000))} of eligible annual LTCG is treated as exempt in this simple estimate.` : businessIncome ? "Business/dividend income uses your selected estimated slab rate." : "Eligible listed-equity short-term gain is estimated at the special rate.";
  $("taxResult").innerHTML = `<span>${escapeHtml(title)}</span><strong>${formatRupees(total)}</strong><div><small>Taxable amount</small><b>${formatRupees(taxable)}</b></div><div><small>Base tax</small><b>${formatRupees(baseTax)}</b></div><div><small>4% cess</small><b>${formatRupees(cess)}</b></div><p>${escapeHtml(notes)}</p>`;
}

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i], next = text[i + 1];
    if (char === '"' && quoted && next === '"') { cell += '"'; i++; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { row.push(cell.trim()); cell = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i++;
      row.push(cell.trim()); cell = "";
      if (row.some(Boolean)) rows.push(row);
      row = [];
    } else cell += char;
  }
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  const headers = rows.shift().map(h => h.toLowerCase());
  const required = ["company", "symbol", "exchange", "date", "quarter", "status"];
  if (!required.every(key => headers.includes(key))) throw new Error(`CSV needs columns: ${required.join(", ")}`);
  return validateResults(rows.map(row => Object.fromEntries(headers.map((key, i) => [key, row[i] || ""]))));
}

function validateResults(items) {
  const required = ["company", "symbol", "exchange", "date", "quarter", "status"];
  return items.map((item, index) => {
    if (!required.every(key => typeof item[key] === "string" && item[key].trim())) throw new Error(`Entry ${index + 1} is missing a required field`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(item.date) || Number.isNaN(localDate(item.date).getTime())) throw new Error(`Entry ${index + 1} has an invalid date`);
    if (!["confirmed", "estimated"].includes(item.status.toLowerCase())) throw new Error(`Entry ${index + 1} has an invalid status`);
    return { ...item, company: item.company.trim(), symbol: item.symbol.trim().toUpperCase(), exchange: item.exchange.trim().toUpperCase(), quarter: item.quarter.trim(), status: item.status.toLowerCase() };
  });
}

async function syncFeed(feedUrl = generatedFeedUrl, quiet = false) {
  const response = await fetch(feedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("Feed must return a JSON array");
  const validated = validateResults(data);
  if (!validated.length) {
    if (!quiet) toast("The feed is valid but currently empty");
    return;
  }
  results = validated;
  save();
  populateExchanges();
  render();
  if (!quiet) toast(`Synced ${validated.length} result dates`);
}

function validateNews(items) {
  const required = ["company", "symbol", "exchange", "publishedAt", "type", "headline"];
  return items.map((item, index) => {
    if (!required.every(key => typeof item[key] === "string" && item[key].trim())) throw new Error(`News item ${index + 1} is missing a required field`);
    if (Number.isNaN(new Date(item.publishedAt).getTime())) throw new Error(`News item ${index + 1} has an invalid timestamp`);
    return { ...item, company: item.company.trim(), symbol: item.symbol.trim().toUpperCase(), exchange: item.exchange.trim().toUpperCase(), summary: item.summary || "", url: item.url || "" };
  });
}

async function syncNews(quiet = false) {
  const response = await fetch(newsFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`News feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("News feed must return a JSON array");
  newsItems = validateNews(data);
  populateExchanges();
  renderNews();
  if (!quiet) toast(`Synced ${newsItems.length} company news items`);
}

async function syncFinancials(quiet = false) {
  const response = await fetch(financialsFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Financials feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("Financials feed must return a JSON array");
  financialItems = data;
  renderCompanySearch();
  if (activeCompany) renderCompanyPage();
  if (!quiet) toast(`Synced ${data.length} company financial summaries`);
}

async function syncMarketNews(quiet = false) {
  const response = await fetch(marketNewsFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Market news feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("Market news feed must return a JSON array");
  marketNewsItems = data;
  renderMarketNews();
  if (!quiet) toast(`Synced ${data.length} market news stories`);
}

async function syncStockAnalysis(quiet = false) {
  const response = await fetch(stockAnalysisFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Stock analysis feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("Stock analysis feed must return a JSON array");
  stockAnalysisItems = data;
  renderStockAnalysis();
  if (!quiet) toast(`Synced daily analysis for ${data.length} stocks`);
}

async function syncPracticePrices(quiet = false) {
  const response = await fetch(practicePricesFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Practice prices feed returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data)) throw new Error("Practice prices feed must return a JSON array");
  practicePrices = data;
  renderPracticePortfolio();
  if (!quiet) toast(`Refreshed practice prices for ${data.length} stocks`);
}

async function syncWatchPredictions(quiet = false) {
  const response = await fetch(watchPredictionsFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Prediction feed returned ${response.status}`);
  const data = await response.json();
  if (!data || !Array.isArray(data.today) || !Array.isArray(data.tomorrow)) throw new Error("Prediction feed is invalid");
  watchPredictionData = data;
  renderWatchPredictions();
  if (!quiet) toast(`Synced ${data.today.length + data.tomorrow.length} stock watches`);
}

async function syncMarketOverview(quiet = false) {
  const response = await fetch(marketOverviewFeedUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Market overview feed returned ${response.status}`);
  const data = await response.json();
  if (!data || !Array.isArray(data.instruments) || typeof data.components !== "object") throw new Error("Market overview feed is invalid");
  marketOverviewData = data;
  renderMarketOverview();
  if (!quiet) toast(`Synced ${data.instruments.length} market instruments`);
}

async function syncVerification(quiet = false) {
  const response = await fetch("/api/results-verification", { cache: "no-store" });
  if (!response.ok) throw new Error(`Verification API returned ${response.status}`);
  verificationData = await response.json();
  renderVerification();
  if (!quiet) toast("Verification and audit status refreshed");
}

function showLogin(message = "") {
  currentUser = null;
  closeMobileMenu();
  $("loginView").hidden = false;
  document.querySelectorAll(".app-protected").forEach(element => element.hidden = true);
  $("loginError").hidden = !message;
  $("loginError").textContent = message;
}

async function bootstrapAuthenticatedApp(user) {
  currentUser = user;
  $("currentUsername").textContent = user.username;
  $("userInitial").textContent = user.username.slice(0, 1).toUpperCase();
  $("loginView").hidden = true;
  document.querySelectorAll(".app-protected").forEach(element => element.hidden = false);
  closeMobileMenu();
  populateExchanges();
  setView("dashboard");
  await Promise.allSettled([
    syncFeed(generatedFeedUrl, true), syncNews(true), syncFinancials(true),
    syncMarketNews(true), syncStockAnalysis(true), syncPracticePrices(true),
    syncWatchPredictions(true), syncMarketOverview(true), syncVerification(true)
  ]);
  openCompanyFromHash();
}

async function checkSession() {
  if (location.protocol === "file:") {
    showLogin("Run the secured app through scripts/job_server.py.");
    return;
  }
  try {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    const payload = await response.json();
    if (payload.authenticated) await bootstrapAuthenticatedApp(payload.user);
    else showLogin();
  } catch {
    showLogin("The secure application server is unavailable.");
  }
}

function formatJobTime(value) {
  if (!value) return "Not run in this session";
  return new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function jobLabel(name) {
  return ({ results: "Results", news: "News", financials: "Financials", "market-news": "Market news", "stock-analysis": "Stock analysis", "practice-prices": "Practice prices", "watch-predictions": "Watch predictions", "market-overview": "Market overview" })[name] || name;
}

function renderJobStatus(state) {
  let running = false;
  for (const name of ["results", "news", "financials", "market-news", "stock-analysis", "practice-prices", "watch-predictions", "market-overview"]) {
    const job = state[name];
    if (!job) continue;
    running ||= job.status === "running";
    const badge = $(`${name}JobBadge`);
    badge.className = `job-badge ${job.status}`;
    badge.textContent = job.status;
    $(`${name}JobTime`).textContent = job.status === "idle" ? "Not run yet" : job.status === "running" ? `Started ${formatJobTime(job.startedAt)}` : `Finished ${formatJobTime(job.finishedAt)}`;
    $(`${name}JobOutput`).textContent = job.output || (job.status === "running" ? "Job is running..." : "No output yet.");
    document.querySelector(`[data-job="${name}"]`).disabled = job.status === "running";
  }
  $("runAllJobsButton").disabled = running;
  clearTimeout(jobPollTimer);
  if (running) jobPollTimer = setTimeout(refreshJobStatus, 1500);
}

async function refreshJobStatus() {
  try {
    const response = await fetch("/api/jobs", { cache: "no-store" });
    if (!response.ok) throw new Error("Job server unavailable");
    $("jobServerNotice").hidden = true;
    renderJobStatus(await response.json());
  } catch {
    $("jobServerNotice").hidden = false;
    document.querySelectorAll(".job-run-button").forEach(button => button.disabled = true);
    $("runAllJobsButton").disabled = true;
  }
}

async function runJob(name) {
  const response = await fetch(`/api/jobs/${name}`, { method: "POST", headers: { "X-QuarterWatch-Action": "run" } });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Could not start ${name} job`);
  toast(`${jobLabel(name)} job started`);
  await waitForJob(name);
}

async function waitForJob(name) {
  return new Promise(resolve => {
    const poll = async () => {
    try {
      const response = await fetch("/api/jobs", { cache: "no-store" });
      const state = await response.json();
      renderJobStatus(state);
      if (state[name]?.status === "running") return setTimeout(poll, 1500);
      if (state[name]?.status === "success") {
        if (name === "results") await syncFeed(generatedFeedUrl, true);
        else if (name === "news") await syncNews(true);
        else if (name === "financials") await syncFinancials(true);
        else if (name === "market-news") await syncMarketNews(true);
        else if (name === "stock-analysis") await syncStockAnalysis(true);
        else if (name === "practice-prices") await syncPracticePrices(true);
        else if (name === "watch-predictions") await syncWatchPredictions(true);
        else await syncMarketOverview(true);
        toast(`${jobLabel(name)} job completed`);
      } else if (state[name]?.status === "failed") toast(`${jobLabel(name)} job failed`);
      resolve();
    } catch (error) {
      toast(`Job status failed: ${error.message}`);
      resolve();
    }
    };
    setTimeout(poll, 500);
  });
}

function download(name, content, type) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = name; link.click(); URL.revokeObjectURL(link.href);
}

function populateExchanges() {
  const current = $("exchangeFilter").value;
  const options = [...new Set([...results, ...newsItems].map(r => r.exchange))].sort();
  $("exchangeFilter").innerHTML = `<option value="">All exchanges</option>${options.map(x => `<option value="${x}">${x}</option>`).join("")}`;
  $("exchangeFilter").value = options.includes(current) ? current : "";
}

$("loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Signing in...";
  try {
    const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Sign in failed");
    event.target.reset();
    await bootstrapAuthenticatedApp(payload.user);
  } catch (error) {
    showLogin(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Sign in securely";
  }
});
$("logoutButton").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  showLogin("You have signed out.");
});
$("userChip").addEventListener("click", () => $("accountDialog").showModal());
$("accountForm").addEventListener("submit", async event => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  if (values.newPassword !== values.confirmPassword) {
    $("accountError").textContent = "New password confirmation does not match.";
    $("accountError").hidden = false;
    return;
  }
  try {
    const response = await fetch("/api/auth/change-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || payload.message || "Password update failed");
    event.target.reset();
    $("accountError").hidden = true;
    $("accountDialog").close();
    toast("Password updated");
  } catch (error) {
    $("accountError").textContent = error.message;
    $("accountError").hidden = false;
  }
});
function closeMobileMenu() {
  $("mobileActionMenu").hidden = true;
  $("mobileMenuButton").setAttribute("aria-expanded", "false");
}

$("mobileMenuButton").addEventListener("click", () => {
  const opening = $("mobileActionMenu").hidden;
  $("mobileActionMenu").hidden = !opening;
  $("mobileMenuButton").setAttribute("aria-expanded", String(opening));
});
$("mobileActionMenu").addEventListener("click", event => {
  const action = event.target.closest("[data-mobile-action]")?.dataset.mobileAction;
  if (!action) return;
  closeMobileMenu();
  if (action === "search") {
    $("searchInput").focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (action === "add") $("entryDialog").showModal();
  else if (action === "import") $("fileInput").click();
  else if (action === "settings") $("settingsButton").click();
  else if (action === "account") $("accountDialog").showModal();
  else if (action === "logout") $("logoutButton").click();
});
document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
  closeMobileMenu();
  setView(tab.dataset.view);
  if (matchMedia("(max-width: 650px)").matches) tab.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
}));
$("taxEstimatorForm").addEventListener("submit", event => {
  event.preventDefault();
  renderTaxEstimate();
});
$("taxProfitType").addEventListener("change", renderTaxEstimate);
$("taxSlabRate").addEventListener("change", renderTaxEstimate);
$("taxProfitAmount").addEventListener("input", renderTaxEstimate);
$("searchInput").addEventListener("input", () => { render(); renderCompanySearch(); });
["exchangeFilter", "statusFilter"].forEach(id => $(id).addEventListener("input", render));
$("companySearchResults").addEventListener("click", event => {
  const result = event.target.closest("[data-search-symbol]");
  if (result) openCompanyPage(result.dataset.searchSymbol, result.dataset.searchExchange);
});
$("addButton").addEventListener("click", () => $("entryDialog").showModal());
$("settingsButton").addEventListener("click", () => {
  $("settingsForm").elements.feedUrl.value = JSON.parse(localStorage.getItem(settingsKey) || "{}").feedUrl || "";
  $("settingsDialog").showModal();
});
$("importButton").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", async event => {
  try {
    const imported = parseCsv(await event.target.files[0].text());
    results = imported; save(); populateExchanges(); render(); toast(`Imported ${imported.length} result dates`);
  } catch (error) { toast(error.message); }
  event.target.value = "";
});
$("entryForm").addEventListener("submit", event => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const item = Object.fromEntries(new FormData(event.target));
  results.push(item); save(); populateExchanges(); render(); event.target.reset(); $("entryDialog").close(); toast("Result date added");
});
$("settingsForm").addEventListener("submit", event => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  localStorage.setItem(settingsKey, JSON.stringify(Object.fromEntries(new FormData(event.target))));
  $("settingsDialog").close(); toast("Feed settings saved");
});
$("clearDataButton").addEventListener("click", () => { results = [...demoResults]; save(); populateExchanges(); render(); toast("Demo data restored"); });
$("syncButton").addEventListener("click", async () => {
  const { feedUrl } = JSON.parse(localStorage.getItem(settingsKey) || "{}");
  try {
    $("syncButton").textContent = "Syncing...";
    await syncFeed(feedUrl || generatedFeedUrl);
  } catch (error) { toast(`Sync failed: ${error.message}`); }
  finally { $("syncButton").textContent = "Sync feed"; }
});
$("syncNewsButton").addEventListener("click", async () => {
  try {
    $("syncNewsButton").textContent = "Refreshing...";
    await syncNews();
  } catch (error) { toast(`News sync failed: ${error.message}`); }
  finally { $("syncNewsButton").textContent = "Refresh news"; }
});
$("marketNewsPlatform").addEventListener("change", renderMarketNews);
$("dashboardView").addEventListener("click", event => {
  const button = event.target.closest("[data-market-symbol]");
  if (button) openCompanyPage(button.dataset.marketSymbol, button.dataset.marketExchange);
});
$("stockSignalFilter").addEventListener("change", renderStockAnalysis);
$("marketInstrumentFilter").addEventListener("change", renderMarketOverview);
$("componentIndexSelect").addEventListener("change", renderMarketComponents);
$("updateMarketOverviewButton").addEventListener("click", async () => {
  try {
    $("updateMarketOverviewButton").textContent = "Updating...";
    await runJob("market-overview");
  } catch (error) { toast(error.message); }
  finally { $("updateMarketOverviewButton").textContent = "Update markets"; }
});
$("marketComponentsBody").addEventListener("click", event => {
  const row = event.target.closest("[data-component-symbol]");
  if (!row) return;
  const company = companyIndex().find(item => item.symbol === row.dataset.componentSymbol && item.exchange === "NSE");
  if (company) openCompanyPage(company.symbol, company.exchange);
  else toast(`${row.dataset.componentSymbol} is not yet indexed in the company feed`);
});
$("watchPredictionFilter").addEventListener("change", renderWatchPredictions);
$("updateWatchPredictionsButton").addEventListener("click", async () => {
  try {
    $("updateWatchPredictionsButton").textContent = "Updating...";
    await runJob("watch-predictions");
  } catch (error) { toast(error.message); }
  finally { $("updateWatchPredictionsButton").textContent = "Update predictions"; }
});
$("watchTodayView").addEventListener("click", event => {
  const card = event.target.closest("[data-watch-symbol]");
  if (card) openCompanyPage(card.dataset.watchSymbol, card.dataset.watchExchange);
});
$("updateStockAnalysisButton").addEventListener("click", async () => {
  try {
    $("updateStockAnalysisButton").textContent = "Updating...";
    await runJob("stock-analysis");
  } catch (error) { toast(error.message); }
  finally { $("updateStockAnalysisButton").textContent = "Update analysis now"; }
});
$("stockAnalysisCards").addEventListener("click", event => {
  const card = event.target.closest("[data-analysis-symbol]");
  if (card) {
    const item = stockAnalysisItems.find(row => row.symbol === card.dataset.analysisSymbol && row.exchange === card.dataset.analysisExchange);
    if (item) openStockChart(item);
  }
});
$("closeStockChartDialog").addEventListener("click", () => $("stockChartDialog").close());
$("practiceBuyButton").addEventListener("click", buyPracticePosition);
["paperInvestment", "paperEntry", "paperExit"].forEach(id => $(id).addEventListener("input", calculatePaperTrade));
$("practicePositions").addEventListener("click", event => {
  const button = event.target.closest("[data-sell-position]");
  if (button) sellPracticePosition(button.dataset.sellPosition);
});
$("refreshPracticePricesButton").addEventListener("click", async () => {
  try {
    $("refreshPracticePricesButton").textContent = "Refreshing...";
    await runJob("practice-prices");
  } catch (error) { toast(error.message); }
  finally { $("refreshPracticePricesButton").textContent = "Refresh practice prices"; }
});
$("updateMarketNewsButton").addEventListener("click", async () => {
  try {
    $("updateMarketNewsButton").textContent = "Updating...";
    await runJob("market-news");
  } catch (error) { toast(error.message); }
  finally { $("updateMarketNewsButton").textContent = "Update news now"; }
});
$("newsList").addEventListener("click", event => {
  if (event.target.closest("a")) return;
  const item = event.target.closest("[data-news-symbol]");
  if (item) openCompanyPage(item.dataset.newsSymbol, item.dataset.newsExchange);
});
document.querySelectorAll(".job-run-button").forEach(button => button.addEventListener("click", async () => {
  try { await runJob(button.dataset.job); }
  catch (error) { toast(error.message); }
}));
$("runAllJobsButton").addEventListener("click", async () => {
  try {
    await Promise.all(["results", "news", "financials", "market-news", "stock-analysis", "practice-prices", "market-overview"].map(runJob));
    await runJob("watch-predictions");
  } catch (error) { toast(error.message); }
});
$("exportButton").addEventListener("click", () => {
  const headers = ["company", "symbol", "exchange", "date", "quarter", "status"];
  const csv = [headers.join(","), ...filteredResults().map(item => headers.map(key => `"${String(item[key]).replaceAll('"', '""')}"`).join(","))].join("\n");
  download("quarterwatch-results.csv", csv, "text/csv");
});
$("resultsBody").addEventListener("click", event => {
  const symbol = event.target.dataset.star;
  if (symbol) {
    const item = companyIndex().find(company => company.symbol === symbol && company.exchange === event.target.dataset.starExchange);
    if (item) toggleWatchlist(item);
    render();
    return;
  }
  const row = event.target.closest("[data-company-symbol]");
  if (row) openCompanyPage(row.dataset.companySymbol, row.dataset.companyExchange);
});
$("companyDirectoryBody").addEventListener("click", event => {
  const row = event.target.closest("[data-directory-symbol]");
  if (row) openCompanyPage(row.dataset.directorySymbol, row.dataset.directoryExchange);
});
$("companyBackButton").addEventListener("click", closeCompanyPage);
$("companyUpdateAllButton").addEventListener("click", updateAllCompanyData);
$("companyDataRetryButton").addEventListener("click", updateAllCompanyData);
$("companyChartRanges").addEventListener("click", event => {
  const button = event.target.closest("[data-chart-range]");
  if (!button) return;
  companyChartRange = button.dataset.chartRange;
  renderCompanyPriceHistory();
});
$("refreshCompanyChartButton").addEventListener("click", async () => {
  try {
    $("refreshCompanyChartButton").disabled = true;
    $("refreshCompanyChartButton").textContent = "Refreshing chart...";
    await loadCompanyFundamentals(true);
  } finally {
    $("refreshCompanyChartButton").disabled = false;
    $("refreshCompanyChartButton").textContent = "Refresh chart";
  }
});
$("companyWatchButton").addEventListener("click", () => {
  if (!activeCompany) return;
  toggleWatchlist(activeCompany);
  renderCompanyPage();
});
$("companyNewsFilter").addEventListener("change", renderCompanyPage);
$("companyAnalyzerFilter").addEventListener("change", renderCompanyAnalyzer);
$("refreshCompanyAnalyzerButton").addEventListener("click", async () => {
  try {
    $("refreshCompanyAnalyzerButton").textContent = "Analyzing...";
    await loadCompanyNewsAnalysis(true);
  } finally {
    $("refreshCompanyAnalyzerButton").textContent = "Analyze 6 months";
  }
});
$("refreshCompanyFundamentalsButton").addEventListener("click", async () => {
  try {
    $("refreshCompanyFundamentalsButton").textContent = "Refreshing...";
    await loadCompanyFundamentals(true);
  } finally {
    $("refreshCompanyFundamentalsButton").textContent = "Refresh fundamentals";
  }
});
$("closeCompanyDialog").addEventListener("click", () => $("companyDialog").close());
$("runFinancialsButton").addEventListener("click", async () => {
  try {
    $("companyDialog").close();
    await runJob("financials");
    setView("jobs");
  } catch (error) { toast(error.message); }
});
$("prevMonth").addEventListener("click", () => { calendarDate.setMonth(calendarDate.getMonth() - 1); renderCalendar(); });
$("nextMonth").addEventListener("click", () => { calendarDate.setMonth(calendarDate.getMonth() + 1); renderCalendar(); });

$("todayDay").textContent = today.toLocaleDateString("en-IN", { weekday: "short" });
$("todayDate").textContent = today.getDate();
$("todayYear").textContent = today.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
renderTaxEstimate();
checkSession();
window.addEventListener("hashchange", () => {
  if (currentUser && !openCompanyFromHash() && !location.hash) closeCompanyPage();
});
