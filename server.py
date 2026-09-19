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


PORT = int(os.environ.get("PORT", "10000"))


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


# =========================================================
# READ REQUEST JSON
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
        raw.decode("utf-8")
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
# BUILD SEARCH FILTERS
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


    # -----------------------------------------------------
    # AIRPORTS
    # -----------------------------------------------------

    departure_airport = get_airport(
        from_code
    )

    arrival_airport = get_airport(
        to_code
    )


    # -----------------------------------------------------
    # PASSENGERS
    # -----------------------------------------------------

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


    passenger_info = PassengerInfo(
        adults=adults,
        children=children,
        infants_on_lap=infants,
        infants_in_seat=0
    )


    # -----------------------------------------------------
    # OUTBOUND
    # -----------------------------------------------------

    segments = [

        FlightSegment(

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

    ]


    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    if return_date:

        segments.append(

            FlightSegment(

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

        )


    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------

    filters = FlightSearchFilters(

        passenger_info=passenger_info,

        flight_segments=segments,

        stops=MaxStops.ANY,

        seat_type=SeatType.ECONOMY,

        sort_by=SortBy.CHEAPEST,

        show_all_results=True
    )


    return filters


# =========================================================
# SERIALIZE RESULT
# =========================================================

def serialize_result(item):

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

    return str(item)


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

                    "apiKeyRequired":
                        False
                }

            )

            return


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
                        "0.9.0"
                }

            )

            return


        # -------------------------------------------------
        # 404
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

            # =============================================
            # READ REQUEST
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
                            "Request body is empty"
                    }

                )

                return


            # =============================================
            # VALIDATION
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

                raise ValueError(
                    "Missing from airport"
                )


            if not to_code:

                raise ValueError(
                    "Missing to airport"
                )


            if not depart_date:

                raise ValueError(
                    "Missing departDate"
                )


            # =============================================
            # LOG
            # =============================================

            print(
                "========================================"
            )

            print(
                "JAWAKK FLI TEST SEARCH"
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
                "========================================"
            )


            # =============================================
            # BUILD FILTERS
            # =============================================

            filters = build_filters(
                search
            )


            print(
                "FILTERS CREATED:"
            )

            print(
                repr(filters)
            )


            # =============================================
            # SEARCH
            # =============================================

            engine = SearchFlights()


            print(
                "SEARCH ENGINE CREATED"
            )


            results = engine.search(

                filters,

                top_n=5

            )


            # =============================================
            # RAW RESULT
            # =============================================

            print(
                "RAW RESULT TYPE:",
                type(results)
            )

            print(
                "RAW RESULT:"
            )

            print(
                repr(results)
            )


            # =============================================
            # NORMALIZE
            # =============================================

            if results is None:

                results = []


            output = []


            for item in results:

                try:

                    output.append(
                        serialize_result(
                            item
                        )
                    )

                except Exception as error:

                    print(
                        "RESULT SERIALIZATION ERROR:",
                        str(error)
                    )


            # =============================================
            # RESPONSE
            # =============================================

            send_json(

                self,

                200,

                {

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
                        (
                            "round-trip"
                            if return_date
                            else "one-way"
                        ),

                    "from":
                        from_code,

                    "to":
                        to_code,

                    "departDate":
                        depart_date,

                    "returnDate":
                        (
                            return_date
                            if return_date
                            else None
                        ),

                    "flights":
                        output,

                    "rawResultType":
                        str(
                            type(results)
                        )

                }

            )


        except Exception as error:

            print(
                "========================================"
            )

            print(
                "FLI ERROR:"
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
# START
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
        "Fli: 0.9.0"
    )

    print(
        "API Key: NOT REQUIRED"
    )

    print(
        "========================================"
    )


    server.serve_forever()


if __name__ == "__main__":

    main()