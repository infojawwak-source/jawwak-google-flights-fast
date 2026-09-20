import os
import json
import traceback
import platform
import sys

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

TEST_TOP_N = 5


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
    ).encode("utf-8")

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
# READ JSON
# =========================================================

def read_json(handler):

    length = int(
        handler.headers.get(
            "Content-Length",
            "0"
        )
    )

    if length <= 0:
        return {}

    raw = handler.rfile.read(
        length
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
# BUILD FILTERS
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
        infants_in_seat=0,
        infants_on_lap=infants
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
# SERIALIZE
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

    if hasattr(
        item,
        "__dict__"
    ):

        return item.__dict__

    return str(item)


# =========================================================
# FLI DIAGNOSTICS
# =========================================================

def collect_fli_info():

    info = {
        "pythonVersion":
            sys.version,

        "platform":
            platform.platform(),

        "fliModule":
            None,

        "fliVersion":
            None,

        "searchClass":
            None,

        "searchMethod":
            None,

        "airportCheck":
            {},

        "models":
            {}
    }


    # -----------------------------------------------------
    # FLI MODULE
    # -----------------------------------------------------

    try:

        import fli

        info["fliModule"] = str(
            fli
        )

        info["fliVersion"] = getattr(
            fli,
            "__version__",
            "unknown"
        )

    except Exception as error:

        info["fliModuleError"] = str(
            error
        )


    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    try:

        import inspect

        info["searchClass"] = str(
            SearchFlights
        )

        info["searchMethod"] = str(
            inspect.signature(
                SearchFlights.search
            )
        )

    except Exception as error:

        info["searchSignatureError"] = str(
            error
        )


    # -----------------------------------------------------
    # AIRPORTS
    # -----------------------------------------------------

    for code in [
        "CAI",
        "JED",
        "DXB",
        "RUH"
    ]:

        try:

            airport = get_airport(
                code
            )

            info["airportCheck"][code] = {

                "exists": True,

                "value":
                    str(airport),

                "repr":
                    repr(airport)
            }

        except Exception as error:

            info["airportCheck"][code] = {

                "exists": False,

                "error":
                    str(error)
            }


    # -----------------------------------------------------
    # ENUMS
    # -----------------------------------------------------

    try:

        info["models"]["SeatType"] = {

            "ECONOMY":
                repr(
                    SeatType.ECONOMY
                ),

            "BUSINESS":
                repr(
                    SeatType.BUSINESS
                ),

            "FIRST":
                repr(
                    SeatType.FIRST
                )
        }

    except Exception as error:

        info["models"]["SeatTypeError"] = str(
            error
        )


    try:

        info["models"]["MaxStops"] = {

            "ANY":
                repr(
                    MaxStops.ANY
                )
        }

    except Exception as error:

        info["models"]["MaxStopsError"] = str(
            error
        )


    try:

        info["models"]["SortBy"] = {

            "CHEAPEST":
                repr(
                    SortBy.CHEAPEST
                )
        }

    except Exception as error:

        info["models"]["SortByError"] = str(
            error
        )


    return info


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
                        False,

                    "mode":
                        "diagnostic"
                }

            )

            return


        # -------------------------------------------------
        # DIAGNOSTIC
        # -------------------------------------------------

        if path == "/api/diagnostic":

            try:

                info = collect_fli_info()

                send_json(

                    self,

                    200,

                    {
                        "ok": True,

                        "mode":
                            "diagnostic",

                        "environment":
                            info
                    }

                )

            except Exception as error:

                send_json(

                    self,

                    500,

                    {
                        "ok": False,

                        "error":
                            str(error)
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
                        "0.9.0",

                    "mode":
                        "diagnostic"
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

                "error":
                    "Not Found"
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
                            "Request body is empty"
                    }

                )

                return


            # =============================================
            # BASIC DATA
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
            # BUILD FILTERS
            # =============================================

            filters = build_filters(
                search
            )


            # =============================================
            # CREATE ENGINE
            # =============================================

            engine = SearchFlights()


            # =============================================
            # SEARCH
            # =============================================

            print(
                "========================================"
            )

            print(
                "FLI DIAGNOSTIC SEARCH"
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
                "Currency:",
                "NONE"
            )

            print(
                "Language:",
                "NONE"
            )

            print(
                "Country:",
                "NONE"
            )

            print(
                "========================================"
            )


            # -------------------------------------------------
            # IMPORTANT:
            #
            # First test exactly what Fli does with its
            # normal search call.
            # -------------------------------------------------

            results = engine.search(

                filters,

                top_n=TEST_TOP_N

            )


            # =============================================
            # RESULT ANALYSIS
            # =============================================

            result_is_none = (
                results is None
            )

            result_type = str(
                type(results)
            )

            result_count = (
                0
                if results is None
                else len(results)
            )


            output = []


            if results:

                for item in results:

                    try:

                        output.append(
                            serialize_result(
                                item
                            )
                        )

                    except Exception as error:

                        output.append({

                            "serializationError":
                                str(error)

                        })


            # =============================================
            # RESPONSE
            # =============================================

            response = {

                "ok":
                    True,

                "diagnostic":
                    True,

                "count":
                    len(output),

                "rawResultType":
                    result_type,

                "rawResultIsNone":
                    result_is_none,

                "rawResultCount":
                    result_count,

                "source":
                    "googleflights",

                "engine":
                    "fli",

                "fliVersion":
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

                "nextStep":
                    (
                        "Fli returned results."
                        if output
                        else
                        "Fli completed the search "
                        "but returned an empty list. "
                        "Check /api/diagnostic and "
                        "Render logs."
                    )

            }


            # =============================================
            # EXTRA DIAGNOSTIC WHEN EMPTY
            # =============================================

            if len(output) == 0:

                response[
                    "emptyResultDiagnosis"
                ] = {

                    "searchCallCompleted":
                        True,

                    "exceptionThrown":
                        False,

                    "fliReturned":
                        "None"
                        if result_is_none
                        else "empty list",

                    "possibleCause":
                        "Google/Fli returned no "
                        "parsed itineraries. "
                        "This does not prove that "
                        "Google returned HTTP 200; "
                        "the installed Fli parser "
                        "may have swallowed/retried "
                        "the underlying request.",

                    "diagnosticEndpoint":
                        "/api/diagnostic"

                }


            send_json(

                self,

                200,

                response

            )


        except Exception as error:

            print(
                "========================================"
            )

            print(
                "FLI DIAGNOSTIC ERROR"
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

                    "ok":
                        False,

                    "diagnostic":
                        True,

                    "error":
                        str(error),

                    "errorType":
                        str(
                            type(error)
                        ),

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
        "JAWAKK GOOGLE FLIGHTS DIAGNOSTIC SERVER"
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
        "Diagnostic endpoint: /api/diagnostic"
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