from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

HOST = "0.0.0.0"
PORT = 5000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "").strip()

INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>eBay Card Price Trend</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
      body { margin: 0; font-family: Arial, sans-serif; background: #f6f8fb; color: #222; }
      main { max-width: 1000px; margin: 2rem auto; padding: 1.5rem; background: white; border-radius: 10px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08); }
      form { display: flex; gap: 0.75rem; margin-bottom: 1rem; }
      input { flex: 1; padding: 0.75rem; border: 1px solid #cfd5dd; border-radius: 8px; }
      button { border: none; border-radius: 8px; padding: 0.75rem 1rem; background: #0064d2; color: white; font-weight: 700; cursor: pointer; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border-bottom: 1px solid #e4e8ef; text-align: left; padding: 0.6rem; vertical-align: top; }
      .chart-wrap { margin: 1.25rem 0; }
    </style>
  </head>
  <body>
    <main>
      <h1>eBay Sold Card Trend Finder</h1>
      <p>Search a card and view recent sold prices.</p>
      <form id="search-form">
        <input id="query" name="query" type="text" placeholder="2020 Panini Prizm Kobe Bryant" required />
        <button type="submit">Search Sold Listings</button>
      </form>
      <p id="status"></p>
      <section class="chart-wrap"><canvas id="trend-chart"></canvas></section>
      <section>
        <table id="results-table">
          <thead><tr><th>Sold Date</th><th>Price</th><th>Title</th></tr></thead>
          <tbody></tbody>
        </table>
      </section>
    </main>
    <script>
      const form = document.getElementById('search-form');
      const statusEl = document.getElementById('status');
      const tableBody = document.querySelector('#results-table tbody');
      const chartCanvas = document.getElementById('trend-chart');
      let trendChart;

      function currency(value) {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
      }

      function drawChart(items) {
        const labels = items.map((item, index) => item.sold_date || `Sale ${index + 1}`);
        const prices = items.map((item) => item.price);
        if (trendChart) trendChart.destroy();
        trendChart = new Chart(chartCanvas, {
          type: 'line',
          data: { labels, datasets: [{ label: 'Sold Price', data: prices, borderColor: '#0064d2', backgroundColor: 'rgba(0,100,210,0.2)', fill: true, tension: 0.2 }] },
          options: { scales: { y: { ticks: { callback: (value) => `$${value}` } } } }
        });
      }

      function renderTable(items) {
        tableBody.innerHTML = '';
        for (const item of items) {
          const row = document.createElement('tr');
          row.innerHTML = `<td>${item.sold_date ?? 'Unknown'}</td><td>${currency(item.price)}</td><td>${item.title}</td>`;
          tableBody.appendChild(row);
        }
      }

      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const query = document.getElementById('query').value.trim();
        if (!query) return;
        statusEl.textContent = 'Searching sold listings...';
        tableBody.innerHTML = '';

        try {
          const response = await fetch(`/api/search?query=${encodeURIComponent(query)}`);
          const payload = await response.json();
          if (!response.ok) {
            statusEl.textContent = payload.error || 'Search failed.';
            if (trendChart) trendChart.destroy();
            return;
          }
          if (!payload.items.length) {
            statusEl.textContent = `No sold items found for "${payload.query}".`;
            if (trendChart) trendChart.destroy();
            return;
          }
          statusEl.textContent = `Found ${payload.count} sold listings for "${payload.query}".`;
          renderTable(payload.items);
          drawChart(payload.items);
        } catch (_error) {
          statusEl.textContent = 'Unable to load data. Please try again.';
          if (trendChart) trendChart.destroy();
        }
      });
    </script>
  </body>
</html>
"""


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _parse_price(raw_price: str) -> float | None:
    match = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", raw_price)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_sold_date(raw_text: str) -> str | None:
    match = re.search(r"Sold\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})", raw_text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _extract_first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return _strip_tags(match.group(1)) if match else None


def fetch_sold_items(query: str, limit: int = 60) -> list[dict[str, Any]]:
    url = (
        "https://www.ebay.com/sch/i.html?"
        f"_nkw={quote(query)}&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"
    )
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})

    with urlopen(req, timeout=20) as response:  # nosec B310
        source = response.read().decode("utf-8", errors="ignore")

    blocks = re.findall(r"(<li[^>]+class=\"[^\"]*s-item[^\"]*\"[\s\S]*?</li>)", source, flags=re.IGNORECASE)

    listings: list[dict[str, Any]] = []
    for block in blocks:
        title = _extract_first(r'class="s-item__title"[^>]*>(.*?)</', block)
        price_text = _extract_first(r'class="s-item__price"[^>]*>(.*?)</', block)
        sold_info = _extract_first(r'(?:class="s-item__title--tagblock"|class="POSITIVE")[^>]*>(.*?)</', block)

        if not title or title.lower().startswith("shop on ebay") or not price_text:
            continue

        price_value = _parse_price(price_text)
        if price_value is None:
            continue

        listings.append(
            {
                "title": title,
                "price": price_value,
                "price_display": price_text,
                "sold_date": _parse_sold_date(sold_info or ""),
            }
        )
        if len(listings) >= limit:
            break

    listings.sort(key=lambda row: row["sold_date"] or "")
    return listings


def _xml_text(node: ElementTree.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def fetch_sold_items_finding_api(query: str, limit: int = 60) -> list[dict[str, Any]]:
    if not EBAY_APP_ID:
        return []

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": EBAY_APP_ID,
        "RESPONSE-DATA-FORMAT": "XML",
        "REST-PAYLOAD": "",
        "keywords": query,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": str(min(limit, 100)),
    }
    url = f"https://svcs.ebay.com/services/search/FindingService/v1?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT, "X-EBAY-SOA-SECURITY-APPNAME": EBAY_APP_ID})

    with urlopen(req, timeout=20) as response:  # nosec B310
        payload = response.read().decode("utf-8", errors="ignore")

    root = ElementTree.fromstring(payload)
    namespace = {"n": "http://www.ebay.com/marketplace/search/v1/services"}
    items = root.findall(".//n:item", namespace)

    listings: list[dict[str, Any]] = []
    for item in items:
        title = _xml_text(item, "n:title")
        price_raw = _xml_text(item, "n:sellingStatus/n:currentPrice")
        sold_date_raw = _xml_text(item, "n:listingInfo/n:endTime")
        if not title or not price_raw:
            continue

        try:
            price = float(price_raw)
        except ValueError:
            continue

        sold_date = None
        if sold_date_raw:
            sold_date = sold_date_raw.split("T", maxsplit=1)[0]

        listings.append(
            {
                "title": title,
                "price": price,
                "price_display": f"${price:,.2f}",
                "sold_date": sold_date,
            }
        )

        if len(listings) >= limit:
            break

    return listings


def fetch_sold_items_with_fallback(query: str, limit: int = 60) -> list[dict[str, Any]]:
    api_error: Exception | None = None
    if EBAY_APP_ID:
        try:
            api_results = fetch_sold_items_finding_api(query, limit=limit)
            if api_results:
                return api_results
        except Exception as exc:  # noqa: BLE001
            api_error = exc

    try:
        return fetch_sold_items(query, limit=limit)
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "eBay blocked the scraping request (HTTP 403). "
                "Set EBAY_APP_ID to use the official Finding API fallback."
            ) from exc
        raise
    except URLError as exc:
        if "403" in str(exc):
            raise RuntimeError(
                "Network/proxy blocked access to eBay (403). "
                "If this persists, set EBAY_APP_ID to use the official API path."
            ) from exc
        if api_error is not None:
            raise RuntimeError(f"API fallback failed first: {api_error}") from api_error
        raise


class EbayTrendHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
        response_bytes = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_html(self, content: str, status_code: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("query", [""])[0].strip()
            if not query:
                self._send_json({"error": "Please enter a card to search."}, 400)
                return

            try:
                items = fetch_sold_items_with_fallback(query)
            except (HTTPError, URLError, TimeoutError, RuntimeError, ElementTree.ParseError) as exc:
                self._send_json({"error": f"Could not reach eBay: {exc}"}, 502)
                return

            self._send_json({"query": query, "count": len(items), "items": items})
            return

        self._send_html("<h1>Not Found</h1>", 404)


def run() -> None:
    server = HTTPServer((HOST, PORT), EbayTrendHandler)
    print(f"Server running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
