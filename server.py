import json
import os
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from fli.models import (
    Airport,
    PassengerInfo,
    SeatType,
    MaxStops,
    SortBy,
    FlightSearchFilters,
    FlightSegment,
)
from fli.search import SearchFlights


# ============================================================
# JAWAKK — Google Flights / Fli Search Server
# ============================================================

PORT = int(os.getenv("PORT", "10000"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "50"))


# ============================================================
# Helpers
# ============================================================

def jsonable(value):
    """
    Convert Fli/Pydantic/Enum/datetime objects into JSON-safe data.
    """
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(k): jsonable(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            jsonable(v)
            for v in value
        ]

    if hasattr(value, "model_dump"):
        try:
            return jsonable(value.model_dump(mode="json"))
        except Exception:
            try:
                return jsonable(value.model_dump())
            except Exception:
                pass

    if hasattr(value, "dict"):
        try:
            return jsonable(value.dict())
        except Exception:
            pass

    if hasattr(value, "value"):
        try:
            return jsonable(value.value)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return jsonable(vars(value))
        except Exception:
            pass

    return str(value)


def normalize_cabin(value):
    value = str(value or "economy").strip().lower()

    mapping = {
        "economy": SeatType.ECONOMY,
        "premium_economy": getattr(
            SeatType,
            "PREMIUM_ECONOMY",
            SeatType.ECONOMY
        ),
        "business": SeatType.BUSINESS,
        "first": SeatType.FIRST,
    }

    return mapping.get(value, SeatType.ECONOMY)


def normalize_stops(value):
    value = str(value or "any").strip().lower()

    mapping = {
        "any": MaxStops.ANY,
        "non_stop": MaxStops.NON_STOP,
        "one_stop": MaxStops.ONE_STOP,
        "two_plus_stops": MaxStops.TWO_PLUS_STOPS,
    }

    return mapping.get(value, MaxStops.ANY)


def normalize_sort(value):
    value = str(value or "cheapest").strip().lower()

    mapping = {
        "cheapest": SortBy.CHEAPEST,
        "price": SortBy.CHEAPEST,
        "duration": getattr(
            SortBy,
            "DURATION",
            SortBy.CHEAPEST
        ),
        "departure_time": getattr(
            SortBy,
            "DEPARTURE_TIME",
            SortBy.CHEAPEST
        ),
        "arrival_time": getattr(
            SortBy,
            "ARRIVAL_TIME",
            SortBy.CHEAPEST
        ),
    }

    return mapping.get(value, SortBy.CHEAPEST)


def make_airport(code):
    """
    Fli Airport is an enum-like airport object.
    """
    code = str(code or "").strip().upper()

    if not code:
        raise ValueError("Airport code is required")

    try:
        return getattr(Airport, code)
    except AttributeError:
        raise ValueError(
            f"Unsupported airport code: {code}"
        )


def build_filters(search):
    """
    Build Fli FlightSearchFilters for one-way or round-trip.
    """

    origin = str(search.get("from") or "").strip().upper()
    destination = str(search.get("to") or "").strip().upper()

    depart_date = str(
        search.get("departDate") or ""
    ).strip()

    return_date = str(
        search.get("returnDate") or ""
    ).strip()

    adults = int(search.get("adults", 1) or 1)
    children = int(search.get("children", 0) or 0)
    infants = int(search.get("infants", 0) or 0)

    if not origin:
        raise ValueError("from is required")

    if not destination:
        raise ValueError("to is required")

    if not depart_date:
        raise ValueError("departDate is required")

    if adults < 1:
        adults = 1

    if children < 0:
        children = 0

    if infants < 0:
        infants = 0

    # --------------------------------------------------------
    # Validate dates
    # --------------------------------------------------------

    datetime.strptime(depart_date, "%Y-%m-%d")

    if return_date:
        datetime.strptime(return_date, "%Y-%m-%d")

    # --------------------------------------------------------
    # Airports
    # --------------------------------------------------------

    from_airport = make_airport(origin)
    to_airport = make_airport(destination)

    # --------------------------------------------------------
    # Passenger info
    # --------------------------------------------------------

    passenger_info = PassengerInfo(
        adults=adults,
        children=children,
        infants_on_lap=infants,
    )

    # --------------------------------------------------------
    # Segments
    # --------------------------------------------------------

    segments = [
        FlightSegment(
            departure_airport=[[from_airport, 0]],
            arrival_airport=[[to_airport, 0]],
            travel_date=depart_date,
        )
    ]

    # --------------------------------------------------------
    # Round Trip
    # --------------------------------------------------------

    if return_date:
        segments.append(
            FlightSegment(
                departure_airport=[[to_airport, 0]],
                arrival_airport=[[from_airport, 0]],
                travel_date=return_date,
            )
        )

    # --------------------------------------------------------
    # Filters
    # --------------------------------------------------------

    filters = FlightSearchFilters(
        passenger_info=passenger_info,
        flight_segments=segments,
        seat_type=normalize_cabin(
            search.get("cabin", "economy")
        ),
        stops=normalize_stops(
            search.get("stops", "any")
        ),
        sort_by=normalize_sort(
            search.get("sort", "cheapest")
        ),
    )

    return filters


# ============================================================
# HTTP Handler
# ============================================================

class Handler(BaseHTTPRequestHandler):

    server_version = "JawwakFli/1.0"

    # --------------------------------------------------------
    # CORS
    # --------------------------------------------------------

    def _cors(self):
        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Accept"
        )

    # --------------------------------------------------------
    # Send JSON
    # --------------------------------------------------------

    def _send_json(self, status, payload):

        body = json.dumps(
            payload,
            ensure_ascii=False,
            default=jsonable
        ).encode("utf-8")

        self.send_response(status)

        self._cors()

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)

        self._cors()

        self.end_headers()

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self):

        path = urlparse(
            self.path
        ).path

        # ----------------------------------------------------
        # Health
        # ----------------------------------------------------

        if path == "/api/health":

            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "jawwak-google-flights-fli",
                    "engine": "fli",
                    "roundTripEngine": "direct-google-rpc",
                    "apiKeyRequired": False,
                }
            )

            return

        # ----------------------------------------------------
        # Root
        # ----------------------------------------------------

        if path == "/":

            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "jawwak-google-flights-fli",
                    "message": "Jawwak Google Flights service is running.",
                }
            )

            return

        # ----------------------------------------------------
        # Not Found
        # ----------------------------------------------------

        self._send_json(
            404,
            {
                "ok": False,
                "error": "Not Found"
            }
        )

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(self):

        path = urlparse(
            self.path
        ).path

        if path != "/api/search-flights":

            self._send_json(
                404,
                {
                    "ok": False,
                    "error": "Not Found"
                }
            )

            return

        # ----------------------------------------------------
        # Read body
        # ----------------------------------------------------

        try:

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            raw_body = self.rfile.read(
                content_length
            )

            body = json.loads(
                raw_body.decode("utf-8")
            )

        except Exception:

            self._send_json(
                400,
                {
                    "ok": False,
                    "error": "Invalid JSON body"
                }
            )

            return

        # ----------------------------------------------------
        # Search
        # ----------------------------------------------------

        try:

            filters = build_filters(body)

            trip_type = (
                "round-trip"
                if body.get("returnDate")
                else "one-way"
            )

            print(
                "=================================================="
            )

            print(
                "[Jawwak] New flight search"
            )

            print(
                f"[Jawwak] From: {body.get('from')}"
            )

            print(
                f"[Jawwak] To: {body.get('to')}"
            )

            print(
                f"[Jawwak] Departure: {body.get('departDate')}"
            )

            print(
                f"[Jawwak] Return: {body.get('returnDate')}"
            )

            print(
                f"[Jawwak] Trip type: {trip_type}"
            )

            print(
                "=================================================="
            )

            # ------------------------------------------------
            # Fli Search
            # ------------------------------------------------

            search_engine = SearchFlights()

            results = search_engine.search(
                filters,
                top_n=MAX_RESULTS,
                currency="EGP",
            )

            results = list(results or [])

            # ------------------------------------------------
            # JSON conversion
            # ------------------------------------------------

            flights = [
                jsonable(item)
                for item in results
            ]

            # ------------------------------------------------
            # Response
            # ------------------------------------------------

            response = {
                "ok": True,
                "count": len(flights),
                "currency": "EGP",
                "cached": False,
                "source": "googleflights",
                "engine": "fli",
                "tripType": trip_type,

                "pricePolicy": (
                    "Price is taken from the same "
                    "Fli Google Flights itinerary; "
                    "no separate return search and "
                    "no manual price summation is used."
                ),

                "flights": flights,
            }

            self._send_json(
                200,
                response
            )

        except Exception as exc:

            print(
                "[Jawwak] Search error:"
            )

            print(
                traceback.format_exc()
            )

            self._send_json(
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "engine": "fli",
                }
            )


# ============================================================
# Start Server
# ============================================================

def main():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    print(
        "=================================================="
    )

    print(
        "Jawwak Google Flights Fli server"
    )

    print(
        f"Listening on port {PORT}"
    )

    print(
        "API Key authentication: DISABLED"
    )

    print(
        f"MAX_RESULTS: {MAX_RESULTS}"
    )

    print(
        "=================================================="
    )

    server.serve_forever()


if __name__ == "__main__":
    main()