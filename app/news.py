import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from defusedxml.ElementTree import ParseError, fromstring
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel, ConfigDict

from .catalog import Stock

logger = logging.getLogger(__name__)
LOOKBACK_DAYS = 7
ARTICLE_LIMIT = 15
FEED_URL = "https://news.google.com/rss/search"
MAX_FEED_BYTES = 1024 * 1024
MAX_HEADLINE_LENGTH = 500
PREFERRED_PUBLISHERS = frozenset({
    "associated press", "dow jones", "dpa-afx", "eqs group", "eqs news",
    "financial times", "finanzen.net", "reuters", "the wall street journal", "wsj",
})


class NewsUnavailable(Exception):
    """The feed could not be fetched or read."""


class Article(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    publisher: str
    published_at: datetime
    url: str


MATERIAL_EVENT = re.compile(
    r"\b(earnings|guidance|revenue|outlook|ceo|acquisition|merger|"
    r"lawsuit|antitrust|regulat\w*|recall|outage|profit\w*|"
    r"quartal\w*|geschäftszahlen|umsatz\w*|prognos\w*|vorstand\w*|"
    r"übernahm\w*|fusion\w*|kartell\w*|rückruf\w*)\b",
    re.IGNORECASE,
)
ROUTINE_COVERAGE = re.compile(
    r"so viel (gewinn|verlust)|"
    r"tendiert am (vormittag|mittag|nachmittag)|"
    r"\b(is|a) .{0,40}stock a buy\b|\baktie \|.*\baktienkurs\b",
    re.IGNORECASE,
)


def matches_company(headline: str, stock: Stock) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", headline, re.IGNORECASE)
        for alias in stock.aliases
    )


def parse_feed(payload: bytes, stock: Stock, now: datetime) -> tuple[Article, ...]:
    channel = fromstring(payload).find("channel")
    if channel is None:
        raise ValueError("RSS channel is missing")

    candidates = []
    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    for item in channel.findall("item"):
        publisher = (item.findtext("source") or "").strip()
        headline = (item.findtext("title") or "").strip()
        if publisher:
            headline = headline.removesuffix(f" - {publisher}").strip()
        if not publisher or len(headline) > MAX_HEADLINE_LENGTH or not matches_company(headline, stock):
            continue
        if ROUTINE_COVERAGE.search(headline):
            continue

        url = (item.findtext("link") or "").strip()
        try:
            target = urlsplit(url)
            published_at = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (ValueError, OverflowError):
            continue
        if target.scheme != "https" or not target.hostname or target.username is not None:
            continue
        if published_at.tzinfo is None or not cutoff <= published_at <= now:
            continue

        candidates.append(
            Article(
                title=headline,
                publisher=publisher,
                published_at=published_at.astimezone(timezone.utc),
                url=url,
            )
        )

    candidates.sort(
        key=lambda article: (
            bool(MATERIAL_EVENT.search(article.title)),
            article.publisher.casefold() in PREFERRED_PUBLISHERS,
            article.published_at,
            article.url,
            article.title,
            article.publisher,
        ),
        reverse=True,
    )
    selected = []
    seen_urls = set()
    seen_titles = set()
    for article in candidates:
        title_key = " ".join(re.findall(r"\w+", article.title.casefold()))
        if article.url in seen_urls or title_key in seen_titles:
            continue
        selected.append(article)
        seen_urls.add(article.url)
        seen_titles.add(title_key)
        if len(selected) == ARTICLE_LIMIT:
            break
    return tuple(selected)


class GoogleNewsFeed:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def fetch(self, stock: Stock) -> tuple[Article, ...]:
        if stock.country == "DE":
            terms = "Aktie OR Geschäftszahlen OR Börse"
            language, edition = "de", "DE:de"
        else:
            terms = f"{stock.ticker} OR earnings OR stock"
            language, edition = "en-US", "US:en"

        params = {
            "q": f'"{stock.search_name}" ({terms}) when:{LOOKBACK_DAYS}d',
            "hl": language,
            "gl": stock.country,
            "ceid": edition,
        }
        try:
            payload = bytearray()
            async with self._client.stream("GET", FEED_URL, params=params) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_FEED_BYTES:
                        raise ValueError("RSS response exceeded the size limit")
            return parse_feed(bytes(payload), stock, datetime.now(timezone.utc))
        except (httpx.HTTPError, ParseError, DefusedXmlException, ValueError) as error:
            logger.warning("RSS request failed for %s (%s)", stock.ticker, type(error).__name__)
            raise NewsUnavailable("The news feed is temporarily unavailable.") from error
