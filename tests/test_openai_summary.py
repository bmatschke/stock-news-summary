import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from openai import AsyncOpenAI

from app.briefing import BriefingUnavailable
from app.catalog import STOCKS
from app.news import Article
from app.openai_summary import OpenAISummarizer


@pytest.mark.parametrize("source_id", [1, 50])
def test_openai_structured_output_resolves_only_provided_source_ids(source_id):
    article = Article(
        title="Apple raises its revenue outlook",
        publisher="Publisher",
        published_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
        url="https://news.google.com/articles/example",
    )

    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["text"]["format"]["type"] == "json_schema"
        assert json.loads(body["input"])["headlines"][0]["title"] == article.title
        assert body["store"] is False
        return httpx.Response(200, json={
            "id": "response_test",
            "object": "response",
            "status": "completed",
            "output": [{
                "id": "message_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{
                    "type": "output_text",
                    "annotations": [],
                    "text": json.dumps({
                        "items": [{
                            "title": " Apple raises its outlook ",
                            "text": article.title,
                            "source_ids": [source_id],
                        }],
                    }),
                }],
            }],
        })

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async with AsyncOpenAI(api_key="test", http_client=http) as client:
            summarize = OpenAISummarizer(client).summarize
            if source_id == 1:
                items = await summarize(STOCKS["AAPL"], (article,))
                assert items[0].title == "Apple raises its outlook"
                assert items[0].sources == (article,)
            else:
                with pytest.raises(BriefingUnavailable, match="invalid citations"):
                    await summarize(STOCKS["AAPL"], (article,))

    asyncio.run(run())


def test_rejected_openai_key_has_an_actionable_message(caplog):
    def respond(request):
        return httpx.Response(401, json={
            "error": {"code": "invalid_api_key", "message": "Rejected key test-secret"},
        })

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async with AsyncOpenAI(api_key="test-secret", http_client=http) as client:
            summarize = OpenAISummarizer(client).summarize
            with pytest.raises(BriefingUnavailable, match=r"Check OPENAI_API_KEY in \.env") as error:
                await summarize(STOCKS["AAPL"], ())
            assert "test-secret" not in str(error.value)

    asyncio.run(run())
    assert "test-secret" not in caplog.text
