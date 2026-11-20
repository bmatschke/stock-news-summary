export interface Listing {
  symbol: string;
  currency: string;
  exchange: { mic: string; name: string; timezone: string };
}

export interface Stock {
  ticker: string;
  name: string;
  listings: Listing[];
}

export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal });
  } catch {
    throw new Error("Could not reach the server. Try again shortly.");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string" ? error.detail : "The request failed. Try again shortly.",
    );
  }
  return (await response.json()) as T;
}
