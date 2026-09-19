# Jawwak Google Flights Server

Standalone Google Flights search service for Jawwak.

## Search strategy

The server first uses `fast-flights-ts`'s direct Google Flights RPC path. If Google returns an RPC response that the current parser cannot decode, the server automatically retries the same structured query through the library's HTML parsing path. This avoids depending on a single Google response format.

The service is search-only. It does not book or ticket flights.

## Endpoints

- `GET /api/health`
- `POST /api/search-flights`

## Authentication

Set `JAWAKK_GOOGLE_FLIGHTS_API_KEY` in Render. Clients must send the same value in the `x-api-key` header.
