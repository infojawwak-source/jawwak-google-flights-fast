import os
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


# =========================================================
# CONFIG
# =========================================================

PORT = int(
    os.environ.get(
        "PORT",
        "10000"
    )
)

MAX_RESULTS = int(
    os.environ.get(
        "MAX_RESULTS",
        "50"
    )
)


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


# =========================================================
# JSON RESPONSE
# =========================================================

def send_json(
    handler,
    status_code,
    payload
):

    body = json.dumps(
        payload,
        ensure_ascii=False,
        default=str
    ).encode(
        "utf-8"
    )

    handler.send_response(
        status_code
    )

    add_cors(
        handler
    )

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    handler.end_headers()

    handler.wfile.write(
        body
    )


# =========================================================
# READ JSON BODY
# =========================================================

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
        raw.decode(
            "utf-8"
        )
    )


# =========================================================
# AIRPORT
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
# CABIN
# =========================================================

def normalize_cabin(value):

    value = str(
        value or "economy"
    ).strip().lower()

    if value == "business":

        return SeatType.BUSINESS

    if value == "first":

        return SeatType.FIRST

    if value in (
        "premium",
        "premium_economy"
    ):

        return SeatType.PREMIUM_ECONOMY

    return SeatType.ECONOMY


# =========================================================
# SORT
# =========================================================

def normalize_sort(value):

    value = str(
        value or "cheapest"
    ).strip().lower()

    if value == "duration":

        return SortBy.DURATION

    if value == "departure_time":

        return SortBy.DEPARTURE_TIME

    if value == "arrival_time":

        return SortBy.ARRIVAL_TIME

    if value == "best":

        return SortBy.BEST

    return SortBy.CHEAPEST


# =========================================================
# PASSENGERS
# =========================================================

def build_passenger_info(search):

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

    infants_in_seat = int(
        search.get(
            "infants_in_seat",
            0
        ) or 0
    )

    infants_on_lap = int(
        search.get(
            "infants_on_lap",
            infants
        ) or 0
    )

    return PassengerInfo(
        adults=adults,
        children=children,
        infants_in_seat=infants_in_seat,
        infants_on_lap=infants_on_lap
    )


# =========================================================
# BUILD FLIGHT SEGMENTS
# =========================================================

def build_segments(search):

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

    departure_airport = get_airport(
        from_code
    )

    arrival_airport = get_airport(
        to_code
    )

    segments = []

    # -----------------------------------------------------
    # OUTBOUND
    # -----------------------------------------------------

    outbound = FlightSegment(
        departure_airport=[
            [
                departure_airport,
                0
            ]
        ],
        arrival_airport=[
            [
                arrival_airport,
                0
            ]
        ],
        travel_date=depart_date
    )

    segments.append(
        outbound
    )

    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    if return_date:

        return_segment = FlightSegment(
            departure_airport=[
                [
                    arrival_airport,
                    0
                ]
            ],
            arrival_airport=[
                [
                    departure_airport,
                    0
                ]
            ],
            travel_date=return_date
        )

        segments.append(
            return_segment
        )

    return segments


# =========================================================
# TRIP TYPE
# =========================================================

def get_trip_type(search):

    return_date = str(
        search.get(
            "returnDate",
            ""
        )
    ).strip()

    # Fli 0.9.0 uses:
    #
    # TripType.ONE_WAY
    # TripType.ROUND_TRIP
    #
    # Importing TripType is avoided because the
    # FlightSearchFilters default is already ONE_WAY
    # and Fli accepts the number used by its enum.

    if return_date:

        from fli.models import TripType

        return TripType.ROUND_TRIP

    from fli.models import TripType

    return TripType.ONE_WAY


# =========================================================
# BUILD FILTERS
# =========================================================

def build_filters(search):

    segments = build_segments(
        search
    )

    passenger_info = build_passenger_info(
        search
    )

    trip_type = get_trip_type(
        search
    )

    cabin = normalize_cabin(
        search.get(
            "cabin",
            "economy"
        )
    )

    sort_by = normalize_sort(
        search.get(
            "sort",
            "cheapest"
        )
    )

    filters = FlightSearchFilters(
        trip_type=trip_type,

        passenger_info=passenger_info,

        flight_segments=segments,

        stops=MaxStops.ANY,

        seat_type=cabin,

        sort_by=sort_by,

        show_all_results=True
    )

    return filters


# =========================================================
# SERIALIZE FLI RESULT
# =========================================================

def serialize_result(item):

    try:

        if hasattr(
            item,
            "model_dump"
        ):

            return item.model_dump()

        if hasattr(
            item,
            "dict"
        ):

            return item.dict()

        if hasattr(
            item,
            "__dict__"
        ):

            return item.__dict__

        return item

    except Exception as error:

        return {
            "serializationError":
                str(error),

            "repr":
                repr(item)
        }


# =========================================================
# HTTP HANDLER
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

        self.send_response(
            204
        )

        add_cors(
            self
        )

        self.end_headers()

    # =====================================================
    # GET
    # =====================================================

    def do_GET(self):

        path = self.path.split(
            "?"
        )[0]

        # -------------------------------------------------
        # ROOT
        # -------------------------------------------------

        if path == "/":

            send_json(
                self,
                200,
                {
                    "ok": True,

                    "service":
                        "jawwak-google-flights-fli",

                    "engine":
                        "fli",

                    "version":
                        "0.9.0",

                    "apiKeyRequired":
                        False
                }
            )

            return

        # -------------------------------------------------
        # HEALTH
        # -------------------------------------------------

        if path == "/api/health":

            send_json(
                self,
                200,
                {
                    "ok": True,

                    "service":
                        "jawwak-google-flights-fli",

                    "engine":
                        "fli",

                    "version":
                        "0.9.0",

                    "roundTripEngine":
                        "direct-google-rpc",

                    "apiKeyRequired":
                        False
                }
            )

            return

        # -------------------------------------------------
        # NOT FOUND
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

        path = self.path.split(
            "?"
        )[0]

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

        if path != "/api/search-flights":

            send_json(
                self,
                404,
                {
                    "ok": False,
                    "error":
                        "Not Found"
                }
            )

            return

        try:

            # =============================================
            # REQUEST
            # =============================================

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
                            "Request body is empty",
                        "engine":
                            "fli"
                    }
                )

                return

            # =============================================
            # BASIC VALIDATION
            # =============================================

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

            if not from_code:

                send_json(
                    self,
                    400,
                    {
                        "ok": False,
                        "error":
                            "Missing from airport",
                        "engine":
                            "fli"
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
                            "Missing to airport",
                        "engine":
                            "fli"
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
                            "Missing departDate",
                        "engine":
                            "fli"
                    }
                )

                return

            # =============================================
            # SEARCH TYPE
            # =============================================

            trip_type = (
                "round-trip"
                if return_date
                else "one-way"
            )

            print(
                "========================================"
            )

            print(
                "JAWAKK GOOGLE FLIGHTS FLI SEARCH"
            )

            print(
                "========================================"
            )

            print(
                "From:",
                from_code
            )

            print(
                "To:",
                to_code
            )

            print(
                "Departure:",
                depart_date
            )

            print(
                "Return:",
                return_date or "NONE"
            )

            print(
                "Trip type:",
                trip_type
            )

            print(
                "========================================"
            )

            # =============================================
            # BUILD FILTERS
            # =============================================

            filters = build_filters(
                search
            )

            print(
                "Fli filters created successfully."
            )

            print(
                "Filters:",
                repr(filters)
            )

            # =============================================
            # SEARCH ENGINE
            # =============================================

            search_engine = SearchFlights()

            print(
                "Fli SearchFlights created."
            )

            # =============================================
            # SEARCH
            #
            # We deliberately do NOT pass currency here
            # initially. This removes one possible source
            # of zero results.
            # =============================================

            results = search_engine.search(
                filters,
                top_n=MAX_RESULTS
            )

            # =============================================
            # NORMALIZE NONE
            # =============================================

            if results is None:

                results = []

            # =============================================
            # RESULTS
            # =============================================

            print(
                "Fli raw result count:",
                len(results)
            )

            output = []

            for item in results:

                try:

                    value = serialize_result(
                        item
                    )

                    output.append(
                        value
                    )

                except Exception as item_error:

                    print(
                        "Result serialization error:",
                        str(item_error)
                    )

            print(
                "Final result count:",
                len(output)
            )

            print(
                "========================================"
            )

            # =============================================
            # RESPONSE
            # =============================================

            response = {
                "ok": True,

                "count":
                    len(output),

                "currency":
                    "EGP",

                "source":
                    "googleflights",

                "engine":
                    "fli",

                "version":
                    "0.9.0",

                "tripType":
                    trip_type,

                "from":
                    from_code,

                "to":
                    to_code,

                "departDate":
                    depart_date,

                "returnDate":
                    return_date or None,

                "flights":
                    output,

                "pricePolicy":
                    "Round-trip price comes "
                    "from the same Google Flights "
                    "Fli itinerary. No manual "
                    "addition of outbound and "
                    "return prices is performed."
            }

            # =============================================
            # EXTRA DEBUG ONLY WHEN ZERO
            # =============================================

            if len(output) == 0:

                response[
                    "diagnostic"
                ] = {

                    "filtersCreated":
                        True,

                    "searchExecuted":
                        True,

                    "fliReturned":
                        "null"
                        if results is None
                        else "empty-list",

                    "maxResults":
                        MAX_RESULTS,

                    "stops":
                        "ANY",

                    "showAllResults":
                        True,

                    "sort":
                        "CHEAPEST",

                    "cabin":
                        str(
                            search.get(
                                "cabin",
                                "economy"
                            )
                        )
                }

            send_json(
                self,
                200,
                response
            )

        # ==============================================
        # ERROR
        # ==============================================

        except Exception as error:

            print(
                "========================================"
            )

            print(
                "FLI SEARCH ERROR"
            )

            print(
                str(error)
            )

            print(
                "========================================"
            )

            traceback.print_exc()

            send_json(
                self,
                500,
                {
                    "ok": False,

                    "error":
                        str(error),

                    "engine":
                        "fli",

                    "version":
                        "0.9.0"
                }
            )


# =========================================================
# START SERVER
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
        "========================================"
    )

    print(
        "Jawwak Google Flights Fli Server"
    )

    print(
        f"Port: {PORT}"
    )

    print(
        "Fli version: 0.9.0"
    )

    print(
        "API key required: NO"
    )

    print(
        "Max results:",
        MAX_RESULTS
    )

    print(
        "========================================"
    )

    server.serve_forever()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()