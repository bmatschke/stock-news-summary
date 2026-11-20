import asyncio
from dataclasses import replace
from datetime import timedelta

import httpx

from app import prices
from app.catalog import STOCKS, Exchange, Listing
from app.main import create_app


def test_simulated_prices_roll_forward_without_changing_previous_points(monkeypatch):
    async def run():
        listing = STOCKS["SIE.DE"].listings[0]
        provider = prices.SimulatedPriceProvider()
        now = 1_795_171_320
        monkeypatch.setattr(prices, "time", lambda: now)

        first = await provider.history(listing)
        assert first.simulated
        assert len(first.points) == 61
        assert first.points[-1].timestamp - first.points[0].timestamp == timedelta(minutes=30)
        assert await provider.history(listing) == first

        now += prices.SAMPLE_SECONDS
        next_series = await provider.history(listing)
        assert next_series.points[:-1] == first.points[1:]
        assert next_series.points[-1].timestamp - first.points[-1].timestamp == timedelta(seconds=30)

    asyncio.run(run())


def test_prices_use_the_selected_listing_and_injected_provider(monkeypatch):
    primary = STOCKS["SIE.DE"].listings[0]
    secondary = Listing("SIE", Exchange("TEST", "Test Exchange", "UTC"), "EUR")
    monkeypatch.setitem(
        STOCKS, "SIE.DE", replace(STOCKS["SIE.DE"], listings=(primary, secondary))
    )
    requested = []

    class RecordingProvider:
        async def history(self, listing):
            requested.append(listing)
            return prices.PriceHistory(source="Test provider", simulated=True, points=())

    async def run():
        app = create_app(price_provider=RecordingProvider())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            default = await client.get("/api/stocks/sie.de/prices")
            assert default.status_code == 200
            assert default.json()["listing"] == {
                "symbol": "SIE",
                "exchange": {"mic": "XETR", "name": "Xetra", "timezone": "Europe/Berlin"},
                "currency": "EUR",
            }
            alternative = await client.get("/api/stocks/SIE.DE/prices?exchange=TEST")
            assert alternative.status_code == 200
            assert alternative.json()["listing"]["exchange"]["mic"] == "TEST"
            assert alternative.json()["simulated"] is True
            assert (await client.get("/api/stocks/SIE.DE/prices?exchange=unknown")).status_code == 404
            assert requested == [primary, secondary]

    asyncio.run(run())
