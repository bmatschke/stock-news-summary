import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app import main
from app.briefing import BriefingItem
from app.main import create_app
from app.news import Article, NewsUnavailable


def test_stock_catalog_and_summary():
    async def load_news(stock):
        assert stock.ticker == "SAP.DE"
        return (
            Article(
                title="SAP reports quarterly results",
                publisher="Example News",
                published_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
                url="https://news.google.com/articles/example",
            ),
        )

    async def summarize(stock, articles):
        return (BriefingItem(title="SAP reports results", text=articles[0].title, sources=articles),)

    async def run():
        app = create_app(load_news, summarize)
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            catalog = (await client.get("/api/stocks")).json()
            assert any(entry["ticker"] == "SAP.DE" and entry["name"] == "SAP" for entry in catalog)
            response = await client.get("/api/stocks/sap.de/summary")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            item = response.json()["items"][0]
            assert item["title"] == "SAP reports results"
            assert item["sources"][0]["publisher"] == "Example News"
            assert (await client.get("/api/stocks/unknown/summary")).status_code == 404

    asyncio.run(run())


def test_feed_outage_is_not_an_empty_result():
    async def load_news(stock):
        raise NewsUnavailable("The news feed is temporarily unavailable.")

    async def summarize(stock, articles):
        raise AssertionError("No headlines were fetched")

    async def run():
        app = create_app(load_news, summarize)
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/stocks/AAPL/summary")).status_code == 503

    asyncio.run(run())


@pytest.mark.parametrize("with_frontend", [False, True])
def test_root_and_api_routing_with_and_without_frontend(tmp_path, monkeypatch, with_frontend):
    build = tmp_path / "dist"
    if with_frontend:
        build.mkdir()
        (build / "index.html").write_text("<h1>Stock News Briefing</h1>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND", build)

    async def run():
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            root = await client.get("/")
            if with_frontend:
                assert root.status_code == 200
                assert "Stock News Briefing" in root.text
            else:
                assert root.status_code == 307
                assert root.headers["location"] == "/docs"

            catalog = await client.get("/api/stocks")
            assert catalog.status_code == 200
            assert any(entry["ticker"] == "SAP.DE" and entry["name"] == "SAP" for entry in catalog.json())

    asyncio.run(run())
