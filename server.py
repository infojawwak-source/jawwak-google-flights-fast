import os
import json
import traceback
import inspect
import importlib.metadata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fli

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


def send_json(
    handler,
    status_code,
    payload
):

    body = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
        indent=2
    ).encode("utf-8")

    handler.send_response(
        status_code
    )

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

    handler.wfile.write(
        body
    )


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
# Safe representation helpers
# =========================================================

def safe_repr(value):

    try:
        return repr(value)

    except Exception:
        return str(value)


def enum_values(enum_class):

    result = {}

    try:

        for name in dir(enum_class):

            if name.startswith("_"):
                continue

            try:

                value = getattr(
                    enum_class,
                    name
                )

                if callable(value):
                    continue

                result[name] = safe_repr(
                    value
                )

            except Exception:
                pass

    except Exception:
        pass

    return result


def model_fields(model_class):

    result = {}

    try:

        fields = getattr(
            model_class,
            "model_fields",
            None
        )

        if fields:

            for name, field in fields.items():

                result[name] = {
                    "annotation":
                        str(
                            getattr(
                                field,
                                "annotation",
                                None
                            )
                        ),
                    "required":
                        bool(
                            getattr(
                                field,
                                "is_required",
                                lambda: False
                            )()
                        )
                }

            return result

    except Exception:
        pass

    try:

        fields = getattr(
            model_class,
            "__fields__",
            None
        )

        if fields:

            for name, field in fields.items():

                result[name] = {
                    "type":
                        str(
                            getattr(
                                field,
                                "type_",
                                None
                            )
                        ),
                    "required":
                        bool(
                            getattr(
                                field,
                                "required",
                                False
                            )
                        )
                }

    except Exception:
        pass

    return result


def class_signature(
    class_object
):

    try:

        return str(
            inspect.signature(
                class_object
            )
        )

    except Exception as error:

        return (
            "SIGNATURE_ERROR: "
            + str(error)
        )


def method_signature(
    object_instance,
    method_name
):

    try:

        method = getattr(
            object_instance,
            method_name
        )

        return str(
            inspect.signature(
                method
            )
        )

    except Exception as error:

        return (
            "SIGNATURE_ERROR: "
            + str(error)
        )


# =========================================================
# Fli version
# =========================================================

def get_fli_version():

    try:

        return importlib.metadata.version(
            "flights"
        )

    except Exception:

        try:

            return importlib.metadata.version(
                "fli"
            )

        except Exception as error:

            return (
                "VERSION_ERROR: "
                + str(error)
            )


# =========================================================
# Airport diagnostics
# =========================================================

def airport_info(code):

    code = str(
        code or ""
    ).strip().upper()

    result = {
        "requested": code,
        "exists": False,
        "value": None,
        "repr": None
    }

    try:

        airport = getattr(
            Airport,
            code
        )

        result["exists"] = True

        result["value"] = str(
            getattr(
                airport,
                "value",
                airport
            )
        )

        result["repr"] = repr(
            airport
        )

    except Exception as error:

        result["error"] = str(
            error
        )

    return result


# =========================================================
# Build diagnostic FlightSegment
# =========================================================

def build_test_segment(
    from_code,
    to_code,
    depart_date
):

    departure_airport = getattr(
        Airport,
        from_code
    )

    arrival_airport = getattr(
        Airport,
        to_code
    )

    segment = FlightSegment(
        departure_airport=[
            [departure_airport, 0]
        ],
        arrival_airport=[
            [arrival_airport, 0]
        ],
        travel_date=depart_date
    )

    return segment


# =========================================================
# Build diagnostic filters
# =========================================================

def build_test_filters(
    from_code,
    to_code,
    depart_date
):

    segment = build_test_segment(
        from_code,
        to_code,
        depart_date
    )

    passenger_info = PassengerInfo(
        adults=1
    )

    filters = FlightSearchFilters(
        passenger_info=passenger_info,
        flight_segments=[
            segment
        ],
        seat_type=SeatType.ECONOMY
    )

    return filters


# =========================================================
# Serialize Fli result
# =========================================================

def serialize_result(
    item
):

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

        return str(item)

    except Exception as error:

        return {
            "serializationError":
                str(error),
            "repr":
                repr(item)
        }


# =========================================================
# Run diagnostic search
# =========================================================

def run_diagnostic_search(
    from_code,
    to_code,
    depart_date
):

    diagnostic = {
        "searchStarted": False,
        "filtersCreated": False,
        "searchEngineCreated": False,
        "searchCalled": False,
        "resultCount": None,
        "results": [],
        "error": None
    }

    try:

        filters = build_test_filters(
            from_code,
            to_code,
            depart_date
        )

        diagnostic[
            "filtersCreated"
        ] = True

        diagnostic[
            "filtersRepr"
        ] = repr(filters)

        diagnostic[
            "filtersType"
        ] = str(
            type(filters)
        )

        search_engine = SearchFlights()

        diagnostic[
            "searchEngineCreated"
        ] = True

        diagnostic[
            "searchMethodSignature"
        ] = method_signature(
            search_engine,
            "search"
        )

        diagnostic[
            "searchStarted"
        ] = True

        # -------------------------------------------------
        # IMPORTANT:
        # Very simple Fli search.
        # No stops.
        # No airline filters.
        # No sort.
        # No currency.
        # -------------------------------------------------

        results = search_engine.search(
            filters,
            top_n=10
        )

        diagnostic[
            "searchCalled"
        ] = True

        if results is None:

            results = []

        diagnostic[
            "resultCount"
        ] = len(results)

        diagnostic[
            "results"
        ] = [
            serialize_result(item)
            for item in results
        ]

        return diagnostic

    except Exception as error:

        diagnostic[
            "error"
        ] = str(error)

        diagnostic[
            "traceback"
        ] = traceback.format_exc()

        return diagnostic


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
        # Root
        # -------------------------------------------------

        if path == "/":

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "service":
                        "jawwak-google-flights-fli-diagnostic",
                    "mode":
                        "diagnostic-only"
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
                        "jawwak-google-flights-fli-diagnostic",
                    "mode":
                        "diagnostic-only",
                    "engine":
                        "fli",
                    "fliVersion":
                        get_fli_version()
                }
            )

            return

        # -------------------------------------------------
        # Fli information
        # -------------------------------------------------

        if path == "/api/diagnostic":

            try:

                search_engine = (
                    SearchFlights()
                )

                payload = {

                    "ok": True,

                    "mode":
                        "diagnostic-only",

                    "python": {
                        "version":
                            os.sys.version
                    },

                    "fli": {

                        "module":
                            str(fli),

                        "version":
                            get_fli_version(),

                        "searchFlightsSignature":
                            class_signature(
                                SearchFlights
                            ),

                        "searchMethodSignature":
                            method_signature(
                                search_engine,
                                "search"
                            )
                    },

                    "models": {

                        "Airport": {
                            "signature":
                                class_signature(
                                    Airport
                                ),
                            "fields":
                                model_fields(
                                    Airport
                                )
                        },

                        "PassengerInfo": {
                            "signature":
                                class_signature(
                                    PassengerInfo
                                ),
                            "fields":
                                model_fields(
                                    PassengerInfo
                                )
                        },

                        "FlightSegment": {
                            "signature":
                                class_signature(
                                    FlightSegment
                                ),
                            "fields":
                                model_fields(
                                    FlightSegment
                                )
                        },

                        "FlightSearchFilters": {
                            "signature":
                                class_signature(
                                    FlightSearchFilters
                                ),
                            "fields":
                                model_fields(
                                    FlightSearchFilters
                                )
                        },

                        "SeatType": {
                            "values":
                                enum_values(
                                    SeatType
                                )
                        },

                        "SortBy": {
                            "values":
                                enum_values(
                                    SortBy
                                )
                        }
                    },

                    "airports": {

                        "CAI":
                            airport_info(
                                "CAI"
                            ),

                        "JED":
                            airport_info(
                                "JED"
                            ),

                        "DXB":
                            airport_info(
                                "DXB"
                            ),

                        "RUH":
                            airport_info(
                                "RUH"
                            )
                    }
                }

                send_json(
                    self,
                    200,
                    payload
                )

            except Exception as error:

                send_json(
                    self,
                    500,
                    {
                        "ok": False,
                        "error":
                            str(error),
                        "traceback":
                            traceback.format_exc()
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

        # -------------------------------------------------
        # Diagnostic search
        # -------------------------------------------------

        if path == "/api/diagnostic-search":

            try:

                search = read_json(
                    self
                )

                from_code = str(
                    search.get(
                        "from",
                        "CAI"
                    )
                ).strip().upper()

                to_code = str(
                    search.get(
                        "to",
                        "JED"
                    )
                ).strip().upper()

                depart_date = str(
                    search.get(
                        "departDate",
                        "2026-10-19"
                    )
                ).strip()

                result = (
                    run_diagnostic_search(
                        from_code,
                        to_code,
                        depart_date
                    )
                )

                send_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "mode":
                            "diagnostic-only",
                        "request": {
                            "from":
                                from_code,
                            "to":
                                to_code,
                            "departDate":
                                depart_date
                        },
                        "fliVersion":
                            get_fli_version(),
                        "diagnostic":
                            result
                    }
                )

            except Exception as error:

                send_json(
                    self,
                    500,
                    {
                        "ok": False,
                        "mode":
                            "diagnostic-only",
                        "error":
                            str(error),
                        "traceback":
                            traceback.format_exc()
                    }
                )

            return

        # -------------------------------------------------
        # Normal search endpoint
        #
        # We intentionally DO NOT run the old search here.
        # This file is diagnostic-only.
        # -------------------------------------------------

        if path == "/api/search-flights":

            send_json(
                self,
                200,
                {
                    "ok": False,
                    "mode":
                        "diagnostic-only",
                    "message":
                        "Normal flight search is disabled in diagnostic mode.",
                    "use":
                        "/api/diagnostic-search"
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
                "error":
                    "Not Found"
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
        "======================================"
    )

    print(
        "Jawwak Fli Diagnostic Server"
    )

    print(
        f"Port: {PORT}"
    )

    print(
        f"Fli version: {get_fli_version()}"
    )

    print(
        "Diagnostic mode ONLY"
    )

    print(
        "======================================"
    )

    server.serve_forever()


if __name__ == "__main__":

    main()