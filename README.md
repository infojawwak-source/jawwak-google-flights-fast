# Jawwak Google Flights Server

Standalone low-volume Google Flights search service for Jawwak.

## Endpoints
- `GET /api/health`
- `POST /api/search-flights`

## Search body
```json
{
  "from":"CAI",
  "to":"JED",
  "departDate":"2026-10-19",
  "returnDate":"2026-10-26",
  "adults":1,
  "children":0,
  "infants":0,
  "cabin":"economy"
}
```

Optional environment variable:
`JAWAKK_GOOGLE_FLIGHTS_API_KEY`

If set, send it as `x-api-key`.

This service is search-only. It does not replace Jawwak's Duffel booking flow.
It uses `fast-flights-ts`, which accesses Google's internal flight-search interface; Google can change or block it.
