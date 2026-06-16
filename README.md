# StockScope India

A dependency-free company intelligence dashboard for Indian listed companies.

## Run

Start the local app server:

```powershell
python scripts/job_server.py
```

On the first start, StockScope creates `data/stockscope.db`, provisions an administrator, and writes the generated initial credentials to `data/initial-admin-password.txt`. Sign in, then delete that password file.

Click the signed-in username in the top bar to change the password. A successful password change automatically removes the temporary initial-password file.

To provide the initial credentials explicitly:

```powershell
python scripts/job_server.py --admin-user admin --admin-password "use-a-long-unique-password"
```

The password is stored using PBKDF2-SHA256 hashing. Sessions are persisted in SQLite and delivered through HttpOnly, SameSite cookies. The database also records job-run history and result-verification evidence.

Then open `http://127.0.0.1:8000`. Use global search or the **Companies** directory to open any indexed company's dedicated research page with available NSE stock context, quarterly filings, upcoming results, contracts/orders, potential positive or risk filings, and all related announcements. The **Jobs** tab can run updater jobs on demand and displays their output.

Opening `index.html` directly still works for reading existing data, but on-demand job buttons require the local server.

### Access from Tailscale

By default the app listens only on this computer. To open it from another trusted Tailscale device, start it with:

```powershell
python scripts/job_server.py --host 0.0.0.0 --allow-remote-jobs
```

Then open `http://TAILSCALE-IP:8000` from your phone or another device. Find the server machine's Tailscale IP with:

```powershell
tailscale ip -4
```

### Mobile use

The site is responsive and can be used from a phone browser. On mobile, use the **Menu** button for jobs, settings, account actions, and imports; swipe the section tabs horizontally to navigate. For quicker access, add the Tailscale URL to the phone's home screen from the browser menu.

Jobs continue running on the computer hosting the server. The phone can start and monitor them while connected, but closing the phone browser does not stop the server-side jobs.

### Learn page

The **Learn** tab includes investing foundations, visual stock-pattern lessons, an indicative Indian equity-tax estimator, broker/platform comparison links, and a high-risk F&O primer. It is educational material rather than personalized investment or tax advice; verify current rules and charges with official sources before acting.

If you want remote devices to view the dashboard but not run updater jobs, omit `--allow-remote-jobs`.

Live NSE quote data can be throttled or rejected by NSE. When that happens, the company page retains all locally indexed research data and provides a direct exchange quote link.

## Market news dashboard

The landing dashboard displays latest and trending market stories. Run it manually with:

```powershell
python scripts/update_market_news.py
```

Publisher RSS/Atom feeds are used where available. Add comma-separated feeds through `MARKET_NEWS_RSS_FEEDS`.

Twitter/X, Instagram, LinkedIn, Facebook, Reddit, and other social platforms may prohibit public scraping or require API credentials. Connect official API output or a compliant JSON feed through `SOCIAL_NEWS_FEED_URLS`. Each item should contain `title` or `text`, `url`, `publishedAt`, and optionally `platform`, `summary`, and `source`.

The dashboard prioritizes stories matched to indexed company names or symbols. Contracts/orders, results, corporate actions, and risk events receive additional priority. Broad Nifty/Sensex commentary remains available below stock-specific stories.

Trending scores are calculated from freshness, repeated topic coverage, market keywords, stock/company matches, and whether a story came from a configured social feed. They do not represent verified social engagement or investment advice.

## Daily stock analysis

The **Stocks** page displays daily technical analysis for priority stocks: companies with upcoming results, companies mentioned in stock-priority news, and optional symbols configured in `STOCK_ANALYSIS_SYMBOLS`.

Run manually:

```powershell
python scripts/update_stock_analysis.py
```

The algorithm combines price versus SMA20/50/200, RSI 14, MACD, 20-day momentum, annualized volatility, volume ratio, and 20-day support/resistance. The confidence percentage measures indicator agreement only. It is not a guarantee of accuracy or future returns.

The default bootstrap source is Yahoo Finance's public chart endpoint. For production trading decisions, use a licensed exchange or broker OHLCV feed and backtest the strategy including costs and slippage.

Click a stock analysis card to open its 90-session closing-price graph, direct NSE/BSE and Yahoo chart links, and a paper-trade simulator. The simulator uses whole shares and calculates amount invested, unused cash, exit value, profit/loss, and percentage return. It does not place real orders and excludes taxes, brokerage, slippage, and other charges.

For practice over several hours, click **Buy for practice**. The open position and buy timestamp are stored in the browser. After waiting, click **Refresh practice prices** to run the intraday price job, then click **Sell** to record realized simulated profit or loss. The refresh job uses recent 15-minute bars and is also included in the scheduled two-hour workflow.

## Today and tomorrow watchlist

The **Today & tomorrow** page ranks a research shortlist using recent company-matched news, exchange events, and the daily technical analysis feed. Social posts and stories containing rumor, buzz, chatter, or other unconfirmed language are explicitly labeled as unverified and receive a much lower score than confirmed sources.

Run the ranking manually:

```powershell
python scripts/update_watch_predictions.py
```

Positive and negative watches describe the direction of the available evidence, not a guaranteed buy or sell outcome. Open any card to inspect the company's full research page before making a decision.

## Indices, components, and metals

The **Markets** page tracks broad indices such as Nifty 50 and Sensex, NSE sector indices, India VIX, and global reference futures for gold, silver, copper, and crude oil. It shows daily, weekly, and monthly changes with recent price charts.

Run the market overview job manually:

```powershell
python scripts/update_market_overview.py
```

The job also requests current NSE constituents for supported indices. Component rows link to the local company research page when the company is indexed. Prices may be delayed, and global commodity futures are not the same as Indian retail spot prices.

## Load full-market data

Use **Import CSV** with these columns:

```text
company,symbol,exchange,date,quarter,status
```

Dates must use `YYYY-MM-DD`; status must be `confirmed` or `estimated`. A starter file is included at `sample-results.csv`.

When served over HTTP, the app automatically loads `data/results.json`. The **Sync feed** button reloads it. You can override it with another JSON URL in settings.

## Automated update job

Run the updater manually:

```powershell
python scripts/update_results.py
```

The updater:

- Pulls forthcoming financial-result board meetings from the NSE Event Calendar for equity and SME listings.
- Merges new dates with future dates from the last successful run.
- Writes `data/results.json`, `data/results.csv`, and `data/update-status.json`.
- Keeps working when one source temporarily fails.
- Labels official NSE event-calendar records as `official-exchange`.
- Labels fallback-provider records as `external-feed`.
- Defaults fallback records to estimated unless the provider explicitly confirms them.
- Labels older retained records without evidence as `legacy-unverified`.
- Stores verification evidence in SQLite when run through the job server.

The companion news job:

```powershell
python scripts/update_news.py
```

It pulls the latest seven days of NSE corporate announcements plus upcoming company events, then writes `data/news.json`, `data/news.csv`, and `data/news-update-status.json`. The dashboard displays these under **News & events**.

The financials job:

```powershell
python scripts/update_financials.py
```

It writes the latest filed quarterly summary for each company to `data/financials.json`. Click any company in the upcoming-results table to view its available revenue, profit/loss, previous-quarter comparison, and related news/events.

The GitHub Actions workflow at `.github/workflows/update-results.yml` runs every two hours and commits changed feeds.

### Add BSE or another fallback source

NSE does not cover BSE-only companies. Add a repository secret named `RESULTS_FALLBACK_URLS` containing one or more comma-separated JSON feed URLs. Each URL can return the standard fields:

```json
[
  {
    "company": "Example Limited",
    "symbol": "500000",
    "exchange": "BSE",
    "date": "2026-07-10",
    "quarter": "Q1 FY27",
    "status": "confirmed"
  }
]
```

The updater also recognizes common field names such as `companyName`, `meetingDate`, `purpose`, and `scripCode`.

For company announcements or news from BSE or a licensed provider, add the `NEWS_FALLBACK_URLS` repository secret. It accepts comma-separated JSON feed URLs with fields such as `company`, `symbol`, `exchange`, `publishedAt`, `type`, `headline`, `summary`, and `url`.

For reliable numeric profit/loss figures, add `FINANCIALS_FALLBACK_URLS`. Feed rows can contain `company`, `symbol`, `exchange`, `quarter`, `periodEnded`, `revenue`, `profitLoss`, `previousRevenue`, `previousProfitLoss`, `currency`, and `sourceUrl`.

## Important

NSE can change or throttle its public website endpoints. Check `data/update-status.json` for source errors. Full and reliable coverage of every listed company, especially BSE-only companies, requires a licensed market-data provider or official exchange feed.

## Six-month company news analyzer

Open a searched company to automatically analyze related news from the previous six months. The analyzer searches multiple RSS queries, removes duplicates, caches results under `data/company-news`, and classifies stories as contracts, results, potential risks, potential positives, or neutral news.

It targets at least 10 stories per stock, but returns fewer when credible coverage is unavailable rather than fabricating articles. Run a refresh from the company page or manually:

```powershell
python scripts/update_company_news.py "Coforge Limited" COFORGE NSE
```

The analyzer requires the local job server and internet access:

```powershell
python scripts/job_server.py
```

The company page also displays an event-based trade suggestion. Recent contracts, positive developments, risk events, sentiment, and available quarter-over-quarter profit direction contribute to a transparent score. Positive scores produce a **Buy-watch** suggestion, negative scores produce a **Sell-review** suggestion, and mixed evidence produces **Hold / Monitor**. These are heuristic research signals, not guaranteed investment advice.

The company fundamentals section retrieves official NSE shareholding patterns and parses quarterly financial XBRL filings on demand. It displays promoter/public ownership, links to the detailed investor filing, and charts available quarterly profit/loss values. Market capitalization is calculated as the NSE last price multiplied by issued shares when both fields are available. Enterprise value remains unavailable unless a reliable debt and cash feed is configured.
