import "./style.css";
import { request, type Stock } from "./api";
import { selectPriceStock } from "./price-chart";

interface Source {
  title: string;
  publisher: string;
  url: string;
  published_at: string;
}

interface Briefing {
  ticker: string;
  company: string;
  items: { title: string; text: string; sources: Source[] }[];
  checked_at: string;
  generated_at: string | null;
  stale: boolean;
}

const form = document.querySelector<HTMLFormElement>("#stock-form")!;
const stock = document.querySelector<HTMLSelectElement>("#stock")!;
const submit = document.querySelector<HTMLButtonElement>("#submit")!;
const status = document.querySelector<HTMLElement>("#status")!;
const panel = document.querySelector<HTMLElement>("#briefing")!;
const company = document.querySelector<HTMLElement>("#company")!;
const ticker = document.querySelector<HTMLElement>("#ticker")!;
const checkedAt = document.querySelector<HTMLTimeElement>("#checked-at")!;
const generated = document.querySelector<HTMLElement>("#generated")!;
const generatedAt = document.querySelector<HTMLTimeElement>("#generated-at")!;
const cached = document.querySelector<HTMLElement>("#cached")!;
const empty = document.querySelector<HTMLElement>("#empty")!;
const developments = document.querySelector<HTMLUListElement>("#developments")!;

const formatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function setTime(element: HTMLTimeElement, timestamp: string) {
  element.dateTime = timestamp;
  element.textContent = formatter.format(new Date(timestamp));
}

function render(briefing: Briefing) {
  company.textContent = briefing.company;
  ticker.textContent = briefing.ticker;
  setTime(checkedAt, briefing.checked_at);
  generated.hidden = !briefing.generated_at || briefing.items.length === 0;
  if (briefing.generated_at) setTime(generatedAt, briefing.generated_at);
  cached.hidden = !briefing.stale;
  empty.hidden = briefing.items.length > 0;
  developments.replaceChildren();

  for (const item of briefing.items) {
    const row = document.createElement("li");
    const title = document.createElement("h3");
    title.textContent = item.title;
    const text = document.createElement("p");
    text.textContent = item.text;

    const citations = document.createElement("ul");
    citations.className = "citations";
    citations.setAttribute("aria-label", "Sources");
    for (const source of item.sources) {
      const citation = document.createElement("li");
      const link = document.createElement("a");
      link.href = source.url;
      link.textContent = source.publisher;
      link.title = source.title;
      link.setAttribute("aria-label", source.publisher + " · " + source.title);
      citation.append(link);
      citations.append(citation);
    }
    row.append(title, text, citations);
    developments.append(row);
  }
  panel.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selected = stock.value;
  if (!selected || submit.disabled) return;

  stock.disabled = true;
  submit.disabled = true;
  submit.textContent = "Checking news…";
  panel.hidden = true;
  status.textContent = "Checking news for " + selected + "…";
  try {
    const briefing = await request<Briefing>(
      "/api/stocks/" + encodeURIComponent(selected) + "/summary",
    );
    render(briefing);
    if (briefing.stale) {
      status.textContent = "Showing cached news for " + briefing.company + ".";
    } else {
      status.textContent = briefing.items.length
        ? "Briefing ready for " + briefing.company + "."
        : "No material news found for " + briefing.company + ".";
    }
  } catch (error) {
    status.textContent = (error as Error).message;
  } finally {
    stock.disabled = false;
    submit.disabled = false;
    submit.textContent = "Get briefing";
  }
});

async function init() {
  try {
    const stocks = await request<Stock[]>("/api/stocks");
    stock.replaceChildren(
      ...stocks.map(({ ticker, name }) => new Option(ticker + " · " + name, ticker)),
    );
    if (stocks.length === 0) return;
    stock.disabled = false;
    submit.disabled = false;
    selectPriceStock(stocks[0]);
    stock.addEventListener("change", () => {
      const selected = stocks.find(entry => entry.ticker === stock.value);
      if (selected) selectPriceStock(selected);
    });
  } catch (error) {
    status.textContent = (error as Error).message;
  }
}

void init();
