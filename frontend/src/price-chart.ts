import { CategoryScale, Chart, LineController, LineElement, LinearScale, PointElement, Tooltip } from "chart.js";
import { request, type Listing, type Stock } from "./api";

interface PriceSeries {
  ticker: string;
  listing: Listing;
  source: string;
  simulated: boolean;
  points: { timestamp: string; price: number }[];
}

const REFRESH_MS = 30_000;
const REQUEST_TIMEOUT_MS = 10_000;

Chart.register(CategoryScale, LineController, LineElement, LinearScale, PointElement, Tooltip);

const card = document.querySelector<HTMLElement>("#price-card")!;
const market = document.querySelector<HTMLElement>("#chart-market")!;
const mode = document.querySelector<HTMLElement>("#chart-mode")!;
const exchangeField = document.querySelector<HTMLElement>("#chart-exchange-field")!;
const exchange = document.querySelector<HTMLSelectElement>("#chart-exchange")!;
const quote = document.querySelector<HTMLElement>("#chart-quote")!;
const price = document.querySelector<HTMLElement>("#chart-price")!;
const asOf = document.querySelector<HTMLTimeElement>("#chart-time")!;
const status = document.querySelector<HTMLElement>("#chart-status")!;
const plot = document.querySelector<HTMLElement>("#chart-plot")!;
const canvas = document.querySelector<HTMLCanvasElement>("#chart-canvas")!;

let selectedStock: Stock | undefined;
let inFlight: AbortController | undefined;
let refreshTimer: number | undefined;
let chart: Chart<"line", number[], string> | undefined;

function render(series: PriceSeries, latest: PriceSeries["points"][number]) {
  const { listing } = series;
  const timeOptions = {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZone: listing.exchange.timezone,
  } as const;
  const time = new Intl.DateTimeFormat(undefined, timeOptions);
  const timeWithZone = new Intl.DateTimeFormat(undefined, { ...timeOptions, timeZoneName: "short" });
  const money = new Intl.NumberFormat(undefined, { style: "currency", currency: listing.currency });

  mode.textContent = series.simulated ? "Simulated prices" : series.source;
  price.textContent = money.format(latest.price);
  asOf.textContent = timeWithZone.format(new Date(latest.timestamp));
  asOf.dateTime = latest.timestamp;
  const chartLabel = series.simulated ? "Simulated price history for " : "Price history for ";
  canvas.setAttribute("aria-label", chartLabel + listing.symbol + " on " + listing.exchange.name);
  quote.hidden = false;
  plot.hidden = false;

  const labels = series.points.map(point => time.format(new Date(point.timestamp)));
  const values = series.points.map(point => point.price);
  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.data.datasets[0].label = listing.currency;
    chart.update();
    return;
  }

  const colors = getComputedStyle(document.documentElement);
  const accent = colors.getPropertyValue("--accent").trim();
  const muted = colors.getPropertyValue("--muted").trim();
  chart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: listing.currency,
        data: values,
        borderColor: accent,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
      }],
    },
    options: {
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        x: { ticks: { color: muted, maxTicksLimit: 4, maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { color: muted, maxTicksLimit: 5 } },
      },
    },
  });
}

async function refresh() {
  refreshTimer = undefined;
  if (document.hidden || !selectedStock || !exchange.value) return;
  const controller = new AbortController();
  inFlight = controller;

  try {
    const params = new URLSearchParams({ exchange: exchange.value });
    const path = "/api/stocks/" + encodeURIComponent(selectedStock.ticker) + "/prices?" + params;
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)]);
    const series = await request<PriceSeries>(path, signal);
    if (signal.aborted) return;

    const latest = series.points.at(-1);
    if (!latest) {
      quote.hidden = true;
      plot.hidden = true;
      status.textContent = "No price history is available for this listing.";
      return;
    }
    render(series, latest);
    status.textContent = "";
  } catch {
    if (!controller.signal.aborted) {
      status.textContent = plot.hidden ? "Could not load prices." : "Could not refresh prices.";
    }
  } finally {
    if (inFlight === controller) {
      inFlight = undefined;
      if (!document.hidden) refreshTimer = window.setTimeout(refresh, REFRESH_MS);
    }
  }
}

function restartRefresh() {
  window.clearTimeout(refreshTimer);
  inFlight?.abort();
  inFlight = undefined;
  void refresh();
}

function selectListing() {
  const listing = selectedStock?.listings.find(entry => entry.exchange.mic === exchange.value);
  if (!listing) return;

  const venue = listing.exchange.name + " (" + listing.exchange.mic + ")";
  market.textContent = [listing.symbol, venue, listing.currency].join(" · ");
  mode.textContent = "";
  quote.hidden = true;
  plot.hidden = true;
  status.textContent = "Loading prices…";
  restartRefresh();
}

export function selectPriceStock(stock: Stock) {
  selectedStock = stock;
  exchange.replaceChildren(...stock.listings.map(
    listing => new Option(listing.exchange.name + " (" + listing.exchange.mic + ")", listing.exchange.mic),
  ));
  exchangeField.hidden = stock.listings.length < 2;
  card.hidden = false;
  selectListing();
}

exchange.addEventListener("change", selectListing);
document.addEventListener("visibilitychange", restartRefresh);
