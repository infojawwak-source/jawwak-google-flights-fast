import os
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fli.models import (
    Airport,
    PassengerInfo,
    SeatType,
    SortBy,
    FlightSearchFilters,
    FlightSegment,
)
from fli.search import SearchFlights


PORT = int(os.environ.get("PORT", "10000"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "50"))


# =========================================================
# CORS
# =========================================================

def add_cors(handler):
    handler.send_header(
        "Access-Control-Allow-Origin",
        "*"
    )
    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, OPTIONS"
    )
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type, Accept"
    )


def send_json(handler, status_code, payload):
    body = json.dumps(
        payload,
        ensure_ascii=False,
        default=str
    ).encode("utf-8")

    handler.send_response(status_code)
    add_cors(handler)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    content_length = int(
        handler.headers.get(
            "Content-Length",
            "0"
        )
    )

    if content_length <= 0:
        return {}

    raw = handler.rfile.read(
        content_length
    )

    if not raw:
        return {}

    return json.loads(
        raw.decode("utf-8")
    )


# =========================================================
# Cabin
# =========================================================

def normalize_cabin(value):

    value = str(
        value or "economy"
    ).strip().lower()

    if value == "business":
        if hasattr(
            SeatType,
            "BUSINESS"
        ):
            return SeatType.BUSINESS

    if value == "first":
        if hasattr(
            SeatType,
            "FIRST"
        ):
            return SeatType.FIRST

    if value in (
        "premium_economy",
        "premium"
    ):
        if hasattr(
            SeatType,
            "PREMIUM_ECONOMY"
        ):
            return SeatType.PREMIUM_ECONOMY

    return SeatType.ECONOMY


# =========================================================
# Sort
# =========================================================

def normalize_sort(value):

    value = str(
        value or "cheapest"
    ).strip().lower()

    if value == "duration":
        if hasattr(
            SortBy,
            "DURATION"
        ):
            return SortBy.DURATION

    if value == "departure_time":
        if hasattr(
            SortBy,
            "DEPARTURE_TIME"
        ):
            return SortBy.DEPARTURE_TIME

    if value == "arrival_time":
        if hasattr(
            SortBy,
            "ARRIVAL_TIME"
        ):
            return SortBy.ARRIVAL_TIME

    return SortBy.CHEAPEST


# =========================================================
# Airport
# =========================================================

def get_airport(code):

    code = str(
        code or ""
    ).strip().upper()

    if not code:
        raise ValueError(
            "Airport code is empty"
        )

    try:
        return getattr(
            Airport,
            code
        )

    except AttributeError:

        raise ValueError(
            f"Unsupported airport code: {code}"
        )


# =========================================================
# Build Filters
# =========================================================

def build_filters(search):

    from_code = str(
        search.get(
            "from",
            ""
        )
    ).strip().upper()

    to_code = str(
        search.get(
            "to",
            ""
        )
    ).strip().upper()

    depart_date = str(
        search.get(
            "departDate",
            ""
        )
    ).strip()

    return_date = str(
        search.get(
            "returnDate",
            ""
        )
    ).strip()

    adults = int(
        search.get(
            "adults",
            1
        ) or 1
    )

    children = int(
        search.get(
            "children",
            0
        ) or 0
    )

    infants = int(
        search.get(
            "infants",
            0
        ) or 0
    )

    # =====================================================
    # Airports
    # =====================================================

    departure_airport = get_airport(
        from_code
    )

    arrival_airport = get_airport(
        to_code
    )

    # =====================================================
    # Passengers
    # =====================================================

    passenger_info = PassengerInfo(
        adults=adults,
        children=children,
        infants=infants
    )

    # =====================================================
    # Flight Segments
    # =====================================================

    segments = []

    # -----------------------------------------------------
    # Outbound
    # -----------------------------------------------------

    outbound = FlightSegment(
        departure_airport=[
            [departure_airport, 0]
        ],
        arrival_airport=[
            [arrival_airport, 0]
        ],
        travel_date=depart_date
    )

    segments.append(
        outbound
    )

    # -----------------------------------------------------
    # Return
    # -----------------------------------------------------

    if return_date:

        return_segment = FlightSegment(
            departure_airport=[
                [arrival_airport, 0]
            ],
            arrival_airport=[
                [departure_airport, 0]
            ],
            travel_date=return_date
        )

        segments.append(
            return_segment
        )

    # =====================================================
    # Filters
    #
    # MaxStops intentionally omitted.
    # =====================================================

    filters = FlightSearchFilters(
        passenger_info=passenger_info,
        flight_segments=segments,
        seat_type=normalize_cabin(
            search.get(
                "cabin",
                "economy"
            )
        ),
        sort_by=normalize_sort(
            search.get(
                "sort",
                "cheapest"
            )
        )
    )

    return filters


# =========================================================
# HTTP Handler
# =========================================================

class Handler(
    BaseHTTPRequestHandler
):

    def log_message(
        self,
        format,
        *args
    ):
        print(
            "%s - %s"
            % (
                self.address_string(),
                format % args
            )
        )

    # =====================================================
    # OPTIONS
    # =====================================================

    def do_OPTIONS(self):

        self.send_response(204)

        add_cors(self)

        self.end_headers()

    # =====================================================
    # GET
    # =====================================================

    def do_GET(self):

        path = self.path.split("?")[0]

        # -------------------------------------------------
        # Root
        # -------------------------------------------------

        if path == "/":

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "service":
                        "jawwak-google-flights-fli",
                    "engine": "fli"
                }
            )

            return

        # -------------------------------------------------
        # Health
        # -------------------------------------------------

        if path == "/api/health":

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "service":
                        "jawwak-google-flights-fli",
                    "engine": "fli",
                    "roundTripEngine":
                        "direct-google-rpc",
                    "apiKeyRequired": False
                }
            )

            return

        # -------------------------------------------------
        # Not Found
        # -------------------------------------------------

        send_json(
            self,
            404,
            {
                "ok": False,
                "error": "Not Found"
            }
        )

    # =====================================================
    # POST
    # =====================================================

    def do_POST(self):

        path = self.path.split("?")[0]

        if path != "/api/search-flights":

            send_json(
                self,
                404,
                {
                    "ok": False,
                    "error": "Not Found"
                }
            )

            return

        try:

            # =================================================
            # Read Request
            # =================================================

            search = read_json(
                self
            )

            if not search:

                send_json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error":
                            "Request body is empty"
                    }
                )

                return

            # =================================================
            # Required Fields
            # =================================================

            from_code = str(
                search.get(
                    "from",
                    ""
                )
            ).strip().upper()

            to_code = str(
                search.get(
                    "to",
                    ""
                )
            ).strip().upper()

            depart_date = str(
                search.get(
                    "departDate",
                    ""
                )
            ).strip()

            if not from_code:

                send_json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error":
                            "Missing from airport"
                    }
                )

                return

            if not to_code:

                send_json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error":
                            "Missing to airport"
                    }
                )

                return

            if not depart_date:

                send_json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error":
                            "Missing departDate"
                    }
                )

                return

            # =================================================
            # Build Filters
            # =================================================

            filters = build_filters(
                search
            )

            print(
                "======================================"
            )

            print(
                "Fli Google Flights Search"
            )

            print(
                json.dumps(
                    search,
                    ensure_ascii=False
                )
            )

            print(
                "======================================"
            )

            # =================================================
            # Search
            # =================================================

            search_engine = SearchFlights()

            results = search_engine.search(
                filters,
                top_n=MAX_RESULTS,
                currency="EGP"
            )

            # =================================================
            # Serialize Results
            # =================================================

            output = []

            for item in results or []:

                try:

                    if hasattr(
                        item,
                        "model_dump"
                    ):

                        value = item.model_dump()

                    elif hasattr(
                        item,
                        "dict"
                    ):

                        value = item.dict()

                    elif hasattr(
                        item,
                        "__dict__"
                    ):

                        value = item.__dict__

                    else:

                        value = item

                    output.append(
                        value
                    )

                except Exception as item_error:

                    print(
                        "Could not serialize result:",
                        item_error
                    )

            # =================================================
            # Response
            # =================================================

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "count": len(output),
                    "currency": "EGP",
                    "source":
                        "googleflights",
                    "engine": "fli",
                    "tripType": (
                        "round-trip"
                        if search.get(
                            "returnDate"
                        )
                        else "one-way"
                    ),
                    "flights": output,
                    "pricePolicy":
                        "Round-trip price comes "
                        "from the same Google Flights "
                        "Fli itinerary. No manual "
                        "addition of outbound and "
                        "return prices is performed."
                }
            )

        except Exception as error:

            print(
                "======================================"
            )

            print(
                "SEARCH ERROR:",
                str(error)
            )

            print(
                "======================================"
            )

            traceback.print_exc()

            send_json(
                self,
                500,
                {
                    "ok": False,
                    "error": str(error),
                    "engine": "fli"
                }
            )


# =========================================================
# Start Server
# =========================================================

def main():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        Handler
    )

    print(
        "Jawwak Google Flights Fli "
        f"server running on port {PORT}"
    )

    server.serve_forever()


if __name__ == "__main__":
    main()