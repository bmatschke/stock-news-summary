from dataclasses import dataclass


@dataclass(frozen=True)
class Exchange:
    mic: str
    name: str
    timezone: str


@dataclass(frozen=True)
class Listing:
    symbol: str
    exchange: Exchange
    currency: str


@dataclass(frozen=True)
class Stock:
    ticker: str
    name: str
    search_name: str
    aliases: tuple[str, ...]
    listings: tuple[Listing, ...]
    country: str = "US"


NASDAQ = Exchange("XNGS", "Nasdaq Global Select Market", "America/New_York")
XETRA = Exchange("XETR", "Xetra", "Europe/Berlin")

STOCKS = {
    stock.ticker: stock
    for stock in (
        Stock("AAPL", "Apple", "Apple", ("Apple", "AAPL"), (Listing("AAPL", NASDAQ, "USD"),)),
        Stock("AMZN", "Amazon", "Amazon", ("Amazon", "AMZN"), (Listing("AMZN", NASDAQ, "USD"),)),
        Stock("MSFT", "Microsoft", "Microsoft", ("Microsoft", "MSFT"), (Listing("MSFT", NASDAQ, "USD"),)),
        Stock("NVDA", "NVIDIA", "NVIDIA", ("NVIDIA", "NVDA"), (Listing("NVDA", NASDAQ, "USD"),)),
        Stock("TSLA", "Tesla", "Tesla", ("Tesla", "TSLA"), (Listing("TSLA", NASDAQ, "USD"),)),
        Stock("BMW.DE", "BMW", "BMW", ("BMW",), (Listing("BMW", XETRA, "EUR"),), country="DE"),
        Stock("FIE.DE", "Fielmann", "Fielmann", ("Fielmann",), (Listing("FIE", XETRA, "EUR"),), country="DE"),
        Stock(
            "RHM.DE", "Rheinmetall", "Rheinmetall", ("Rheinmetall",),
            (Listing("RHM", XETRA, "EUR"),), country="DE",
        ),
        Stock("SAP.DE", "SAP", "SAP", ("SAP",), (Listing("SAP", XETRA, "EUR"),), country="DE"),
        Stock(
            "SIE.DE", "Siemens", "Siemens AG", ("Siemens AG", "Siemens-Aktie"),
            (Listing("SIE", XETRA, "EUR"),), country="DE",
        ),
    )
}
