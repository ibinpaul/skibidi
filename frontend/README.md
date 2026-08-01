# XILO Frontend

TypeScript + React + Vite frontend for the movie booking flow.

## Run

```bash
cd frontend
npm install
npm run dev
```

If the backend is running on a different host or port, set:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## What it does

- Sends movie requests to the recommender endpoint.
- Sends theater-specific seat requests to the seat RBA endpoint.
- Shows a separate owner-style analytics area for demand and accessibility signals.
