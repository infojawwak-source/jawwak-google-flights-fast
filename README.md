# Jawwak Google Flights Server V4

Round-trip safety update:
- Never pairs a separately searched return flight with an outbound fare.
- Accepts a round-trip result only when both outbound and return legs are present in the same parsed Google itinerary.
- Keeps Google's returned round-trip itinerary price as the total fare.
- Filters out zero/negative prices.
