# Stock News Briefing

A local FastAPI and TypeScript app that turns recent company news into up to three short developments with source links. It supports ten US and German stocks and uses public Google News RSS for headlines. The only API credential is an OpenAI key.

## Run locally

You need Python 3.10+, uv, Node.js 22.12+ with npm, and an OpenAI Platform API key. Run the commands from the project root. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

Create the local configuration file.

~~~sh
cp .env.example .env
~~~

Set `OPENAI_API_KEY` in `.env`. The default model is `gpt-5.4-mini`. You can set `OPENAI_MODEL` to another model available to your project that supports structured outputs. Git ignores `.env`.

Install the locked dependencies, build the browser page, and start FastAPI.

~~~sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
uv run --locked uvicorn app.main:app --env-file .env
~~~

Choose a ticker and click **Get briefing**. If OpenAI rejects the credentials, check the key in `.env` and restart FastAPI so it loads the updated file. [Open the app](http://127.0.0.1:8000/)

For an API-only run, skip the npm commands and use the interactive docs or call the endpoint directly. [Swagger UI](http://127.0.0.1:8000/docs)

~~~sh
curl -i http://127.0.0.1:8000/api/stocks/SAP.DE/summary
~~~

`GET /api/stocks` lists supported ticker symbols and their listings. `GET /api/stocks/{ticker}/summary` returns titled developments with their sources, timestamps, and a `stale` flag. An empty `items` list means no suitable coverage was found. Unsupported tickers return 404. A temporary upstream failure returns 503 when there is no briefing within the allowed cache age.

## Backend structure

Stock endpoints live in an `APIRouter`. New sets of endpoints can use their own router and register it in the app factory before the frontend mount. [Stock routes](app/routers/stocks.py) · [App factory](app/main.py)

The application lifespan creates and closes the HTTP clients and briefing service. Route handlers receive the service through a FastAPI dependency. Tests can supply replacement news and summarization providers through the app factory. [Application lifespan](app/lifespan.py)

## News selection

- Finanzen.net's company news pages distinguish stock-specific coverage, issuer announcements, and broader market news. The app follows the company-specific approach and looks for earnings, guidance, management changes, deals, and regulatory developments. [SAP news](https://www.finanzen.net/nachrichten/alle/sap) · [Apple news](https://www.finanzen.net/nachrichten/alle/apple)
- The stock catalog resolves tickers to company names and search terms. Each search uses a US or German edition. The parser checks headline aliases and timestamps against a rolling seven-day window, removes duplicate links and headlines, and ranks candidates by event terms, preferred publishers, and publication time. [Stock catalog](app/catalog.py)
- OpenAI receives up to 15 headlines, their publishers, and dates. It groups reports about the same event and picks up to three developments. The server resolves model-provided source IDs to the RSS links, so citations point to articles actually supplied to the model. Briefings use headlines as evidence and links follow Google News through to the publishers.

Google News RSS coverage and ranking can vary. During spot checks the app found several candidates for SAP and Apple and far fewer for Fielmann. The empty state is appropriate when a company has sparse or immaterial coverage. A dedicated feed with entity tags would improve ranking and widen coverage if this became a production service.

## Freshness and reuse

| Situation | Behavior |
| --- | --- |
| A briefing was checked less than 15 minutes ago | Every visitor for that ticker gets the cached briefing. |
| The last check found no material developments | Recheck after 5 minutes. |
| A briefing needs a refresh | The next request starts one refresh for the ticker. Other requests can share the cached briefing while it runs. At 60 minutes since the last successful check, requests must wait for a refresh or receive a 503. |
| Selected article inputs are identical | Update the check time and reuse the briefing, citations, and generation time. |
| Selected article inputs change | Generate a new briefing. An empty selection skips OpenAI. |
| An upstream call fails | Preserve any eligible cached result and wait 60 seconds before retrying that ticker. |

The cache is in memory and bounded by the stock catalog. The service coalesces simultaneous requests per ticker and caps concurrent refreshes at six per process. The app exposes both the feed check time and the briefing generation time because a successful recheck often needs no model call.

For thousands of visits per day, upstream load depends on the number of active tickers and how often article inputs change. Twenty tickers continually viewed over an eight-hour session would trigger roughly 640 RSS checks at the 15-minute interval, with OpenAI calls on initial or changed selections. To run multiple API workers, move the briefs and fingerprints to Redis and coordinate refreshes with per-ticker leases. Track cache hits, fingerprint changes, upstream latency, and failures to tune the intervals and capacity. An ingestion worker could later store shared article metadata and enqueue affected tickers as articles arrive.

## Simulated price chart

The chart shows the configured listing symbol, exchange MIC, currency, and exchange-local time. For example, Siemens uses `SIE` on Xetra (`XETR`) in EUR. The five US listings use Nasdaq Global Select Market (`XNGS`) in USD. [Xetra reference data](https://api.twelvedata.com/stocks?mic_code=XETR) · [Nasdaq reference data](https://api.twelvedata.com/stocks?mic_code=XNGS)

`GET /api/stocks/{ticker}/prices` uses the default listing. Pass `?exchange=XETR` to request a specific configured venue. The simulated provider returns the same samples for each listing and 30-second time bucket. The synthetic timeline runs independently of exchange sessions and the chart requires no price-data account.

The chart waits for each request to finish before scheduling the next refresh 30 seconds later. Requests time out after 10 seconds. Polling pauses in hidden tabs and refreshes immediately when the tab becomes visible. Changing listings cancels the previous request.

Add venues and listings to the stock catalog. The chart shows an exchange selector for stocks with multiple configured listings. A future market-data adapter can implement `PriceProvider.history(listing)` and be supplied through `create_app(price_provider=...)`. [Stock catalog](app/catalog.py) · [Price provider](app/prices.py)

## Testing strategy

Run the automated backend tests and the frontend type check and build.

~~~sh
uv run --locked pytest
npm --prefix frontend run build
~~~

The pytest suite uses RSS fixtures and mocked upstream responses so it runs without API keys or network access. It covers news selection, citation validation, cache reuse and concurrent refreshes, errors and empty results, and simulated price history and exchange selection. The frontend build checks TypeScript before bundling.

For a live smoke test with a configured key, generate briefings for `AAPL` and `SAP.DE`. Open the citations and check that they support each titled development. Request the same ticker again within 15 minutes and confirm both briefing timestamps match. Select `SIE.DE` and verify the chart is labeled **SIE · Xetra (XETR) · EUR** with simulated prices. Wait for a chart refresh, then switch away from and back to the tab to check that it updates on return.

## Tools used

Python, FastAPI, HTTPX, defusedxml, the OpenAI Python SDK, TypeScript, Chart.js, Vite, and pytest. OpenAI Codex assisted with source research, design, implementation, and verification.
