from datetime import datetime, timezone
from hashlib import sha256
from math import pi, sin
from time import time
from typing import Protocol

from pydantic import BaseModel

from .catalog import Listing

SAMPLE_SECONDS = 30
WINDOW_SECONDS = 30 * 60


class PricePoint(BaseModel):
    timestamp: datetime
    price: float


class PriceHistory(BaseModel):
    source: str
    simulated: bool
    points: tuple[PricePoint, ...]


class PriceSeries(PriceHistory):
    ticker: str
    listing: Listing


class PriceProvider(Protocol):
    async def history(self, listing: Listing) -> PriceHistory: ...


class SimulatedPriceProvider:
    async def history(self, listing: Listing) -> PriceHistory:
        latest_bucket = int(time()) // SAMPLE_SECONDS
        first_bucket = latest_bucket - WINDOW_SECONDS // SAMPLE_SECONDS
        key = f"{listing.exchange.mic}:{listing.symbol}"
        seed = int.from_bytes(sha256(key.encode()).digest()[:4], "big")
        baseline = 70 + seed % 180
        phase = (seed % 360) * pi / 180

        # Each bucket is independent of when a visitor opened the page.
        points = []
        for bucket in range(first_bucket, latest_bucket + 1):
            movement = 0.015 * sin(bucket / 13 + phase) + 0.004 * sin(bucket / 2 + phase)
            points.append(
                PricePoint(
                    timestamp=datetime.fromtimestamp(bucket * SAMPLE_SECONDS, tz=timezone.utc),
                    price=round(baseline * (1 + movement), 2),
                )
            )

        return PriceHistory(
            source="Local simulator",
            simulated=True,
            points=tuple(points),
        )
