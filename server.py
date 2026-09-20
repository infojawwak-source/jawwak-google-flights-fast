import json
import os
import sys
import platform
import traceback
import inspect
import socket
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# =========================================================
# FLI IMPORT
# =========================================================

try:
    import fli

    from fli.models import (
        Airport,
        PassengerInfo,
        SeatType,
        FlightSearchFilters,
        FlightSegment,
    )

    from fli.search import SearchFlights

    FLI_IMPORT_OK = True
    FLI_IMPORT_ERROR = None

except Exception as e:
    FLI_IMPORT_OK = False
    FLI_IMPORT_ERROR = repr(e)

# =========================================================
# CONFIG
# =========================================================

PORT = int(os.environ.get("PORT", "10000"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "20"))

# =========================================================
# CORS
# =========================================================

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept",
    }


def send_json(handler, payload, status=200):
    body = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    handler.send_response(status)

    for key, value in cors_headers().items():
        handler.send_header(key, value)

    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()

    handler.wfile.write(body)


# =========================================================
# AIRPORT
# =========================================================

def get_airport(code):
    code = str(code or "").strip().upper()

    if not code:
        raise ValueError("Airport code is empty")

    if not hasattr(Airport, code):
        raise ValueError(
            f"Airport {code} is not available in Fli Airport enum"
        )

    return getattr(Airport, code)


# =========================================================
# BUILD SEARCH
# =========================================================

def build_filters(search):
    from_code = search.get("from")
    to_code = search.get("to")
    depart_date = search.get("departDate")
    return_date = search.get("returnDate")

    adults = int(search.get("adults", 1) or 1)
    children = int(search.get("children", 0) or 0)
    infants = int(search.get("infants", 0) or 0)

    cabin = str(
        search.get("cabin", "economy")
    ).strip().lower()

    if cabin == "business":
        seat_type = SeatType.BUSINESS
    elif cabin == "first":
        seat_type = SeatType.FIRST
    elif cabin in ("premium", "premium_economy"):
        seat_type = SeatType.PREMIUM_ECONOMY
    else:
        seat_type = SeatType.ECONOMY

    departure_airport = get_airport(from_code)
    arrival_airport = get_airport(to_code)

    segments = [
        FlightSegment(
            departure_airport=[
                [departure_airport, 0]
            ],
            arrival_airport=[
                [arrival_airport, 0]
            ],
            travel_date=depart_date,
        )
    ]

    trip_type = "one-way"

    # Round trip
    if return_date:
        trip_type = "round-trip"

        segments.append(
            FlightSegment(
                departure_airport=[
                    [arrival_airport, 0]
                ],
                arrival_airport=[
                    [departure_airport, 0]
                ],
                travel_date=return_date,
            )
        )

    passenger_info = PassengerInfo(
        adults=adults,
        children=children,
        infants_on_lap=infants,
    )

    # IMPORTANT:
    # We intentionally do NOT specify MaxStops or SortBy here.
    # This removes enum compatibility as a possible cause.

    filters = FlightSearchFilters(
        passenger_info=passenger_info,
        flight_segments=segments,
        seat_type=seat_type,
    )

    return filters, trip_type


# =========================================================
# SAFE REPRESENTATION
# =========================================================

def safe_repr(value, limit=1500):
    try:
        text = repr(value)

        if len(text) > limit:
            text = text[:limit] + "...TRUNCATED"

        return text

    except Exception as e:
        return f"<repr failed: {e!r}>"


# =========================================================
# SEARCH
# =========================================================

def run_fli_search(search):
    diagnostics = {
        "startedAt": datetime.utcnow().isoformat() + "Z",
        "fliImportOk": FLI_IMPORT_OK,
        "fliImportError": FLI_IMPORT_ERROR,
    }

    if not FLI_IMPORT_OK:
        return None, diagnostics, "Fli import failed"

    filters, trip_type = build_filters(search)

    diagnostics["tripType"] = trip_type
    diagnostics["filtersType"] = str(type(filters))
    diagnostics["filtersRepr"] = safe_repr(filters)

    diagnostics["searchClass"] = safe_repr(SearchFlights)

    try:
        diagnostics["searchSignature"] = str(
            inspect.signature(SearchFlights.search)
        )
    except Exception as e:
        diagnostics["searchSignatureError"] = repr(e)

    search_engine = SearchFlights()

    diagnostics["searchEngineType"] = str(type(search_engine))

    # -----------------------------------------------------
    # FIRST ATTEMPT
    # -----------------------------------------------------

    try:
        diagnostics["attempt"] = "search(filters, top_n, currency)"

        started = datetime.utcnow()

        raw_result = search_engine.search(
            filters,
            top_n=MAX_RESULTS,
            currency="EGP",
        )

        elapsed = (
            datetime.utcnow() - started
        ).total_seconds()

        diagnostics["elapsedSeconds"] = elapsed
        diagnostics["rawType"] = str(type(raw_result))
        diagnostics["rawIsNone"] = raw_result is None

        if raw_result is None:
            diagnostics["rawCount"] = 0
            diagnostics["resultState"] = "NONE"

            return raw_result, diagnostics, None

        try:
            diagnostics["rawCount"] = len(raw_result)
        except Exception:
            diagnostics["rawCount"] = None

        diagnostics["resultState"] = "RESULT"

        if isinstance(raw_result, (list, tuple)):
            diagnostics["firstItemType"] = (
                str(type(raw_result[0]))
                if len(raw_result) > 0
                else None
            )

            if len(raw_result) > 0:
                diagnostics["firstItemRepr"] = safe_repr(
                    raw_result[0],
                    3000,
                )

        return raw_result, diagnostics, None

    except Exception as e:

        diagnostics["resultState"] = "EXCEPTION"
        diagnostics["exceptionType"] = str(type(e))
        diagnostics["exception"] = str(e)
        diagnostics["exceptionRepr"] = repr(e)

        diagnostics["traceback"] = traceback.format_exc()

        return None, diagnostics, str(e)


# =========================================================
# NETWORK DIAGNOSTIC
# =========================================================

def network_diagnostic():

    result = {
        "dns": {},
        "connections": {},
    }

    # Google domains commonly involved in Fli requests.
    hosts = [
        "www.google.com",
        "google.com",
    ]

    for host in hosts:

        try:
            addresses = socket.getaddrinfo(
                host,
                443,
                type=socket.SOCK_STREAM,
            )

            unique = []

            for item in addresses:
                try:
                    addr = item[4][0]

                    if addr not in unique:
                        unique.append(addr)

                except Exception:
                    pass

            result["dns"][host] = {
                "ok": True,
                "addresses": unique[:10],
            }

        except Exception as e:

            result["dns"][host] = {
                "ok": False,
                "error": repr(e),
            }

    # Raw TCP connection test.
    for host in hosts:

        try:

            started = datetime.utcnow()

            sock = socket.create_connection(
                (host, 443),
                timeout=8,
            )

            elapsed = (
                datetime.utcnow() - started
            ).total_seconds()

            sock.close()

            result["connections"][host] = {
                "ok": True,
                "elapsedSeconds": elapsed,
            }

        except Exception as e:

            result["connections"][host] = {
                "ok": False,
                "error": repr(e),
            }

    return result


# =========================================================
# HANDLER
# =========================================================

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(
            "[HTTP]",
            format % args,
            flush=True,
        )

    def do_OPTIONS(self):
        send_json(
            self,
            {
                "ok": True,
                "options": True,
            },
            204,
        )

    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    def do_GET(self):

        path = urlparse(
            self.path
        ).path

        if path == "/api/health":

            send_json(
                self,
                {
                    "ok": True,
                    "service": "jawwak-google-flights-fli",
                    "engine": "fli",
                    "fliVersion": "0.9.0",
                    "apiKeyRequired": False,
                },
            )

            return

        if path == "/api/diagnostic":

            network = network_diagnostic()

            payload = {
                "ok": True,
                "diagnostic": True,
                "environment": {
                    "pythonVersion": sys.version,
                    "platform": platform.platform(),
                    "hostname": socket.gethostname(),
                    "fliImported": FLI_IMPORT_OK,
                    "fliImportError": FLI_IMPORT_ERROR,
                    "fliModule": (
                        safe_repr(fli)
                        if FLI_IMPORT_OK
                        else None
                    ),
                },
                "network": network,
                "note": (
                    "This endpoint tests Render DNS/TCP connectivity "
                    "to Google. It does not perform a flight search."
                ),
            }

            send_json(self, payload)

            return

        send_json(
            self,
            {
                "ok": False,
                "error": "Not Found",
            },
            404,
        )

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    def do_POST(self):

        path = urlparse(
            self.path
        ).path

        if path != "/api/search-flights":

            send_json(
                self,
                {
                    "ok": False,
                    "error": "Not Found",
                },
                404,
            )

            return

        try:

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            raw_body = self.rfile.read(
                content_length
            )

            search = json.loads(
                raw_body.decode("utf-8")
            )

        except Exception as e:

            send_json(
                self,
                {
                    "ok": False,
                    "error": "Invalid JSON",
                    "details": repr(e),
                },
                400,
            )

            return

        required = [
            "from",
            "to",
            "departDate",
        ]

        missing = [
            key
            for key in required
            if not search.get(key)
        ]

        if missing:

            send_json(
                self,
                {
                    "ok": False,
                    "error": "Missing required fields",
                    "missing": missing,
                },
                400,
            )

            return

        print(
            "\n========================================",
            flush=True,
        )

        print(
            "FINAL FLI DIAGNOSTIC SEARCH",
            flush=True,
        )

        print(
            json.dumps(
                search,
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

        print(
            "========================================\n",
            flush=True,
        )

        try:

            raw_result, diagnostics, error = (
                run_fli_search(search)
            )

            if error:

                send_json(
                    self,
                    {
                        "ok": False,
                        "error": error,
                        "engine": "fli",
                        "diagnostic": diagnostics,
                    },
                    500,
                )

                return

            if raw_result is None:

                send_json(
                    self,
                    {
                        "ok": True,
                        "diagnostic": True,
                        "count": 0,
                        "rawResultType": "NoneType",
                        "rawResultIsNone": True,
                        "rawResultCount": 0,
                        "source": "googleflights",
                        "engine": "fli",
                        "fliVersion": "0.9.0",
                        "tripType": diagnostics.get(
                            "tripType"
                        ),
                        "from": search.get("from"),
                        "to": search.get("to"),
                        "departDate": search.get(
                            "departDate"
                        ),
                        "returnDate": search.get(
                            "returnDate"
                        ),
                        "flights": [],
                        "diagnostics": diagnostics,
                        "network": network_diagnostic(),
                    },
                )

                return

            # Convert raw Fli objects to JSON safely.
            flights = []

            if isinstance(
                raw_result,
                (list, tuple),
            ):

                for item in raw_result:

                    try:

                        flights.append(
                            json.loads(
                                json.dumps(
                                    item,
                                    default=str,
                                )
                            )
                        )

                    except Exception as e:

                        flights.append(
                            {
                                "serializationError": repr(e),
                                "repr": safe_repr(item),
                            }
                        )

            else:

                flights = [
                    json.loads(
                        json.dumps(
                            raw_result,
                            default=str,
                        )
                    )
                ]

            send_json(
                self,
                {
                    "ok": True,
                    "count": len(flights),
                    "currency": "EGP",
                    "source": "googleflights",
                    "engine": "fli",
                    "fliVersion": "0.9.0",
                    "tripType": diagnostics.get(
                        "tripType"
                    ),
                    "from": search.get("from"),
                    "to": search.get("to"),
                    "departDate": search.get(
                        "departDate"
                    ),
                    "returnDate": search.get(
                        "returnDate"
                    ),
                    "flights": flights,
                    "diagnostics": diagnostics,
                },
            )

        except Exception as e:

            print(
                traceback.format_exc(),
                flush=True,
            )

            send_json(
                self,
                {
                    "ok": False,
                    "error": str(e),
                    "exceptionType": str(type(e)),
                    "traceback": traceback.format_exc(),
                    "engine": "fli",
                },
                500,
            )


# =========================================================
# SERVER
# =========================================================

if __name__ == "__main__":

    print(
        "========================================",
        flush=True,
    )

    print(
        "Jawwak Google Flights - FINAL DIAGNOSTIC",
        flush=True,
    )

    print(
        f"Python: {sys.version}",
        flush=True,
    )

    print(
        f"Port: {PORT}",
        flush=True,
    )

    print(
        f"Fli import: {FLI_IMPORT_OK}",
        flush=True,
    )

    if FLI_IMPORT_ERROR:
        print(
            f"Fli import error: {FLI_IMPORT_ERROR}",
            flush=True,
        )

    print(
        "========================================",
        flush=True,
    )

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler,
    )

    print(
        f"Server listening on port {PORT}",
        flush=True,
    )

    server.serve_forever()