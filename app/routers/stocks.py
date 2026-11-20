from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..briefing import Briefing, BriefingService, BriefingUnavailable
from ..catalog import STOCKS, Listing, Stock
from ..news import NewsUnavailable
from ..prices import PriceProvider, PriceSeries

router = APIRouter(prefix="/api/stocks")


class StockOption(BaseModel):
    ticker: str
    name: str
    listings: tuple[Listing, ...]


async def get_briefing_service(request: Request) -> BriefingService:
    return request.app.state.briefings


async def get_stock(ticker: str) -> Stock:
    stock = STOCKS.get(ticker.strip().upper())
    if stock is None:
        raise HTTPException(status_code=404, detail="Choose a ticker from the supported list.")
    return stock


async def get_price_provider(request: Request) -> PriceProvider:
    return request.app.state.price_provider


@router.get("")
async def stocks() -> list[StockOption]:
    return [
        StockOption(ticker=stock.ticker, name=stock.name, listings=stock.listings)
        for stock in STOCKS.values()
    ]


@router.get("/{ticker}/summary")
async def summary(
    response: Response,
    stock: Annotated[Stock, Depends(get_stock)],
    briefings: Annotated[BriefingService, Depends(get_briefing_service)],
) -> Briefing:
    try:
        briefing = await briefings.get(stock)
    except (BriefingUnavailable, NewsUnavailable) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    response.headers["Cache-Control"] = "no-store"
    return briefing


@router.get("/{ticker}/prices")
async def prices(
    response: Response,
    stock: Annotated[Stock, Depends(get_stock)],
    provider: Annotated[PriceProvider, Depends(get_price_provider)],
    exchange: str | None = None,
) -> PriceSeries:
    listing = stock.listings[0]
    if exchange is not None:
        mic = exchange.strip().upper()
        listing = next((entry for entry in stock.listings if entry.exchange.mic == mic), None)
        if listing is None:
            raise HTTPException(status_code=404, detail="This stock has no configured listing on that exchange.")

    history = await provider.history(listing)
    response.headers["Cache-Control"] = "no-store"
    return PriceSeries(
        ticker=stock.ticker,
        listing=listing,
        source=history.source,
        simulated=history.simulated,
        points=history.points,
    )
