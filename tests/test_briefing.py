import asyncio
from datetime import datetime, timezone

import pytest

from app.briefing import (
    EMPTY_SECONDS,
    FRESH_SECONDS,
    MAX_AGE_SECONDS,
    BriefingItem,
    BriefingService,
)
from app.catalog import STOCKS
from app.news import Article, NewsUnavailable

STOCK = STOCKS["AAPL"]
ARTICLE = Article(
    title="Apple raises its revenue outlook",
    publisher="Publisher",
    published_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
    url="https://news.google.com/articles/example",
)


def test_refresh_reuses_unchanged_articles_and_regenerates_after_a_correction():
    async def run():
        clock = 0
        loads = 0
        generations = 0
        articles = (ARTICLE,)

        async def load_news(stock):
            nonlocal loads
            loads += 1
            return articles

        async def summarize(stock, selected):
            nonlocal generations
            generations += 1
            return (BriefingItem(title=selected[0].title, text=selected[0].title, sources=selected),)

        service = BriefingService(load_news, summarize, clock=lambda: clock)
        first = await service.get(STOCK)
        assert await service.get(STOCK) == first
        assert (loads, generations) == (1, 1)

        clock += FRESH_SECONDS
        assert (await service.get(STOCK)).stale
        await asyncio.sleep(0)
        reused = await service.get(STOCK)
        assert reused.generated_at == first.generated_at
        assert reused.checked_at > first.checked_at
        assert not reused.stale
        assert (loads, generations) == (2, 1)

        articles = (ARTICLE.model_copy(update={"title": "Apple maintains its revenue outlook"}),)
        clock += FRESH_SECONDS
        assert (await service.get(STOCK)).stale
        await asyncio.sleep(0)
        updated = await service.get(STOCK)
        assert updated.items[0].text == articles[0].title
        assert updated.items[0].title == articles[0].title
        assert (loads, generations) == (3, 2)
        await service.close()

    asyncio.run(run())


def test_concurrent_cold_requests_share_one_refresh_even_if_one_client_cancels():
    async def run():
        release = asyncio.Event()
        started = asyncio.Event()
        loads = 0

        async def load_news(stock):
            nonlocal loads
            loads += 1
            started.set()
            await release.wait()
            return (ARTICLE,)

        async def summarize(stock, selected):
            return (BriefingItem(title=ARTICLE.title, text=ARTICLE.title, sources=selected),)

        service = BriefingService(load_news, summarize)
        first = asyncio.create_task(service.get(STOCK))
        second = asyncio.create_task(service.get(STOCK))
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second).items
        assert loads == 1
        await service.close()

    asyncio.run(run())


def test_upstream_failure_preserves_briefing_until_the_hard_cutoff():
    async def run():
        clock = 0
        loads = 0

        async def load_news(stock):
            nonlocal loads
            loads += 1
            if loads > 1:
                raise NewsUnavailable("RSS failed")
            return (ARTICLE,)

        async def summarize(stock, selected):
            return (BriefingItem(title=ARTICLE.title, text=ARTICLE.title, sources=selected),)

        service = BriefingService(load_news, summarize, clock=lambda: clock)
        first = await service.get(STOCK)
        clock = FRESH_SECONDS
        assert (await service.get(STOCK)).stale
        await asyncio.sleep(0)
        assert (await service.get(STOCK)).checked_at == first.checked_at
        assert loads == 2

        clock = MAX_AGE_SECONDS
        with pytest.raises(NewsUnavailable, match="RSS failed"):
            await service.get(STOCK)
        assert loads == 3
        await service.close()

    asyncio.run(run())


def test_empty_result_is_rechecked_earlier_and_uses_no_openai_call():
    async def run():
        clock = 0
        loads = 0

        async def load_news(stock):
            nonlocal loads
            loads += 1
            return ()

        async def summarize(stock, selected):
            pytest.fail("The summarizer should not run without sources")

        service = BriefingService(load_news, summarize, clock=lambda: clock)
        first = await service.get(STOCK)
        assert not first.items
        assert first.generated_at is None
        clock = EMPTY_SECONDS - 1
        assert await service.get(STOCK) == first
        clock = EMPTY_SECONDS
        assert not (await service.get(STOCK)).stale
        assert loads == 2
        await service.close()

    asyncio.run(run())
