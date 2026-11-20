from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from app.catalog import STOCKS
from app.news import parse_feed

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def feed(entries):
    rss = Element("rss")
    channel = SubElement(rss, "channel")
    for headline, path, days_old in entries:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = headline + " - Publisher"
        SubElement(item, "link").text = "https://news.google.com/" + path
        SubElement(item, "source").text = "Publisher"
        SubElement(item, "pubDate").text = format_datetime(NOW - timedelta(days=days_old))
    return tostring(rss, encoding="utf-8")


def test_feed_selection_filters_stale_unrelated_and_duplicate_headlines():
    entries = [
        ("SAP-Aktie endet kaum verändert", "routine", 0),
        ("Saputo announces plans to expand", "unrelated", 1),
        ("SAP veröffentlicht Geschäftszahlen", "earnings", 1),
        ("SAP veröffentlicht Geschäftszahlen", "syndicated", 2),
        ("SAP meldet Umsatzplus", "stale", 8),
        ("SAP stellt neue Prognose vor", "future", -1),
        ("SAP-Vorstand kündigt Rücktritt an", "board", 2),
    ]

    selected = parse_feed(feed(entries), STOCKS["SAP.DE"], NOW)
    assert [article.url.rsplit("/", 1)[-1] for article in selected] == [
        "earnings", "board", "routine",
    ]
    assert selected[0].title == "SAP veröffentlicht Geschäftszahlen"
    assert selected == parse_feed(feed(reversed(entries)), STOCKS["SAP.DE"], NOW)


def test_empty_channel_differs_from_non_feed():
    assert parse_feed(feed([]), STOCKS["AAPL"], NOW) == ()
    with pytest.raises(ValueError, match="RSS channel"):
        parse_feed(b"<html />", STOCKS["AAPL"], NOW)
