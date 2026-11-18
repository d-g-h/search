# Search

Search sample property listings by price, bedrooms, city, or description. The React frontend uses Tailwind CSS and calls a Python API for ranked, paginated results.

## Run with Docker

```sh
docker compose up --build --detach --wait web
```

Open http://127.0.0.1:8000. Docker installs frontend dependencies with `npm ci`, builds the UI, and starts the Python server that serves the UI and API.

Run the tests inside the running container.

```sh
docker compose exec -T web python -m unittest discover -s backend/tests -v
```

Use `docker compose down` to stop the application.

## Search and ranking

All filters must match. Price and bedroom limits are inclusive. City matches the whole name, and the keyword matches a phrase in the description. Both ignore case and extra whitespace. Listings from different feeds are kept as separate records.

```text
recency   = 2 ^ (-days since listing / 30)
budgetFit = max(0, 1 - abs(price - targetBudget) / targetBudget)
score     = 100 × (0.70 × budgetFit + 0.30 × recency)
```

The target budget affects rank. `maxPrice` sets a hard ceiling. The 70/30 split favors price fit while rewarding newer listings. Prices equally far above and below the target get the same budget fit. Without a budget, the score is `100 × recency`. Future listing dates count as zero days old.

A new listing priced exactly at the target scores 100. After 30 days it scores 85. Results sort by unrounded score, then by source and listing ID, before pagination. Scanning and sorting the in-memory dataset keeps the implementation small for the supplied data.

## API

Try [a ranked search in Reston](http://127.0.0.1:8000/api/listings?city=Reston&targetBudget=600000&pageSize=3).

`GET /api/listings` accepts `minPrice`, `maxPrice`, `minBedrooms`, `city`, `keyword`, `targetBudget`, `page`, and `pageSize`. Pages start at 1. Page size defaults to 6 and accepts 1–100. Invalid parameters return HTTP 400. No matches return HTTP 200 with an empty `items` array.

Search logic and unit tests live in `backend/search.py` and `backend/tests/`. The HTTP adapter is `backend/server.py`, and the UI is `frontend/main.tsx`.
