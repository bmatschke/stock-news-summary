import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from openai import AsyncOpenAI

from .briefing import BriefingService, LoadNews, Summarize
from .news import GoogleNewsFeed
from .openai_summary import DEFAULT_MODEL, OpenAISummarizer


@asynccontextmanager
async def lifespan(
    app: FastAPI,
    *,
    load_news: LoadNews | None = None,
    summarize: Summarize | None = None,
) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        if load_news is None:
            http = await stack.enter_async_context(
                httpx.AsyncClient(timeout=8, headers={"User-Agent": "StockNewsBriefing/0.1"})
            )
            load_news = GoogleNewsFeed(http).fetch

        if summarize is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            client = None
            if api_key:
                client = await stack.enter_async_context(
                    AsyncOpenAI(api_key=api_key, timeout=25, max_retries=0)
                )
            model = os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
            summarize = OpenAISummarizer(client, model).summarize

        briefings = BriefingService(load_news, summarize)
        app.state.briefings = briefings
        try:
            yield
        finally:
            await briefings.close()
