# ebay sold card trend finder

A lightweight Python web app that searches **sold eBay listings** for a sports card and shows:

- A line chart of sold prices
- A table of recently sold items (title, sold date, and price)

## Run locally

```bash
python3 app.py
```

Then open `http://localhost:5000`.

### Optional: use eBay Finding API (recommended)

To avoid occasional scraping blocks (`403 Forbidden`), provide your eBay app ID:

```bash
export EBAY_APP_ID="your-ebay-app-id"
python3 app.py
```

The app will try the official Finding API first and fall back to scraping sold listings if needed.

## Notes

- The app uses only Python standard-library modules on the backend.
- It uses eBay's public search results page (`LH_Sold=1` + `LH_Complete=1`) and parses listing cards.
- eBay markup can change over time, so selectors may need periodic updates.
