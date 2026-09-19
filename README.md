# Jawwak Google Flights Debug V6

Diagnostic-only server. It calls fast-flights-ts with a true `round-trip` query and exposes the parsed raw result structure through `/api/debug-roundtrip` so we can determine where the outbound/return itinerary and total price live.

Do not connect this service to the main Jawwak frontend. After the diagnostic response is understood, build the production implementation from the observed structure.
