# Jawwak Google Flights — Fli Engine

Experimental standalone Google Flights service for testing genuine round-trip itineraries.

## Engine
Uses the open-source `fli` Python library, which talks to Google's internal Flights RPC directly and supports one-way and round-trip searches.

## Endpoints
- GET `/api/health`
- POST `/api/search-flights`

## Environment
- `PORT` — Render supplies this automatically.
- `JAWAKK_GOOGLE_FLIGHTS_API_KEY` — optional but recommended.
- `MAX_RESULTS` — optional, default 50.

## Test body
```json
{
  "from": "CAI",
  "to": "JED",
  "departDate": "2026-10-19",
  "returnDate": "2026-10-26",
  "adults": 1,
  "children": 0,
  "infants": 0,
  "cabin": "economy"
}
```

This version intentionally returns the complete parsed itinerary objects rather than converting them into the old Jawwak schema. The first goal is to verify that Google/fli returns both legs and one itinerary-level price without any manual pairing.
