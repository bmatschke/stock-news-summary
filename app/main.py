from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .briefing import LoadNews, Summarize
from .lifespan import lifespan
from .prices import PriceProvider, SimulatedPriceProvider
from .routers import stocks

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "dist"


async def index() -> RedirectResponse:
    return RedirectResponse("/docs")


def create_app(
    load_news: LoadNews | None = None,
    summarize: Summarize | None = None,
    *,
    price_provider: PriceProvider | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Stock News Briefing",
        lifespan=partial(lifespan, load_news=load_news, summarize=summarize),
    )
    app.state.price_provider = SimulatedPriceProvider() if price_provider is None else price_provider
    app.include_router(stocks.router)

    # Register API routers before the catch-all static mount.
    if FRONTEND.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    else:
        app.add_api_route("/", index, methods=["GET"], include_in_schema=False)

    return app


app = create_app()
