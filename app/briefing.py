import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from pydantic import BaseModel, ConfigDict

from .catalog import Stock
from .news import Article, NewsUnavailable

FRESH_SECONDS = 15 * 60
EMPTY_SECONDS = 5 * 60
MAX_AGE_SECONDS = 60 * 60
RETRY_SECONDS = 60
MAX_CONCURRENT_REFRESHES = 6


class BriefingUnavailable(Exception):
    """A briefing could not be generated at this time."""


class BriefingItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    text: str
    sources: tuple[Article, ...]


class Briefing(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    company: str
    items: tuple[BriefingItem, ...]
    checked_at: datetime
    generated_at: datetime | None
    stale: bool = False


LoadNews = Callable[[Stock], Awaitable[tuple[Article, ...]]]
Summarize = Callable[[Stock, tuple[Article, ...]], Awaitable[tuple[BriefingItem, ...]]]


@dataclass(frozen=True)
class CachedBriefing:
    briefing: Briefing
    fingerprint: str
    checked_at: float


def article_fingerprint(articles: tuple[Article, ...]) -> str:
    content = "\n".join(article.model_dump_json() for article in articles)
    return hashlib.sha256(content.encode()).hexdigest()


class BriefingService:
    def __init__(self, load_news: LoadNews, summarize: Summarize, clock=monotonic):
        self._load_news = load_news
        self._summarize = summarize
        self._clock = clock
        self._cache: dict[str, CachedBriefing] = {}
        self._pending: dict[str, asyncio.Task[Briefing]] = {}
        self._retry_after: dict[str, float] = {}

    async def get(self, stock: Stock) -> Briefing:
        ticker = stock.ticker
        now = self._clock()
        cached = self._cache.get(ticker)
        if cached is not None:
            age = now - cached.checked_at
            fresh_for = FRESH_SECONDS if cached.briefing.items else EMPTY_SECONDS
            if age < fresh_for:
                return cached.briefing
            if cached.briefing.items and age < MAX_AGE_SECONDS:
                self._start_refresh(stock, now)
                return cached.briefing.model_copy(update={"stale": True})

        task = self._start_refresh(stock, now)
        if task is None:
            raise BriefingUnavailable("The briefing is temporarily unavailable. Try again shortly.")
        return await asyncio.shield(task)

    def _start_refresh(self, stock: Stock, now: float) -> asyncio.Task[Briefing] | None:
        ticker = stock.ticker
        if ticker in self._pending:
            return self._pending[ticker]
        if now < self._retry_after.get(ticker, 0) or len(self._pending) >= MAX_CONCURRENT_REFRESHES:
            return None

        # This method runs without yielding, so only one refresh per ticker is registered.
        task = asyncio.create_task(self._refresh(stock))
        self._pending[ticker] = task
        task.add_done_callback(self._observe_result)
        return task

    async def _refresh(self, stock: Stock) -> Briefing:
        ticker = stock.ticker
        try:
            articles = await self._load_news(stock)
            checked_at = self._clock()
            checked_at_utc = datetime.now(timezone.utc)
            fingerprint = article_fingerprint(articles)
            cached = self._cache.get(ticker)

            if cached is not None and cached.fingerprint == fingerprint:
                briefing = cached.briefing.model_copy(update={"checked_at": checked_at_utc})
            else:
                items = await self._summarize(stock, articles) if articles else ()
                briefing = Briefing(
                    ticker=ticker,
                    company=stock.name,
                    items=items,
                    checked_at=checked_at_utc,
                    generated_at=datetime.now(timezone.utc) if articles else None,
                )

            self._cache[ticker] = CachedBriefing(briefing, fingerprint, checked_at)
            self._retry_after.pop(ticker, None)
            return briefing
        except (BriefingUnavailable, NewsUnavailable):
            self._retry_after[ticker] = self._clock() + RETRY_SECONDS
            raise
        finally:
            self._pending.pop(ticker, None)

    @staticmethod
    def _observe_result(task: asyncio.Task[Briefing]) -> None:
        # A refresh that served a cached result may have no request awaiting it.
        if not task.cancelled():
            task.exception()

    async def close(self) -> None:
        tasks = tuple(self._pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
