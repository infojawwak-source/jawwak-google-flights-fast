import json
import os
import traceback
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
    TripType,
)
from fli.search import SearchFlights


PORT = int(os.environ.get("PORT", "10000"))
API_KEY = os.environ.get("JAWAKK_GOOGLE_FLIGHTS_API_KEY", "").strip()
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "50"))


def enum_value(x):
    return getattr(x, "value", x)


def jsonable(x):
    if x is None or isinstance(x, (str, int, float, bool)):
        return x

    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]

    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}

    if hasattr(x, "model_dump"):
        try:
            return jsonable(x.model_dump(mode="json"))
        except Exception:
            pass

    if hasattr(x, "__dict__"):
        return {
            str(k): jsonable(v)
            for k, v in vars(x).items()
            if not str(k).startswith("_")
        }

    return str(x)


def airport_enum(code):
    code = str(code or "").upper().strip()

    if not code:
        raise ValueError("Missing airport code")

    try:
        return Airport[code]
    except KeyError:
        for a in Airport:
            if str(enum_value(a)).upper() == code:
                return a

    raise ValueError(f"Unsupported IATA airport code: {code}")


def cabin_enum(cabin):
    c = str(cabin or "economy").lower()

    if c in ("economy", "coach"):
        return SeatType.ECONOMY

    if c in ("premium_economy", "premium-economy", "premium"):
        return getattr(
            SeatType,
            "PREMIUM_ECONOMY",
            SeatType.ECONOMY,
        )

    if c == "business":
        return SeatType.BUSINESS

    if c == "first":
        return SeatType.FIRST

    raise ValueError(f"Unsupported cabin: {cabin}")


def build_filters(q):
    from_code = str(q.get("from", "")).upper().strip()
    to_code = str(q.get("to", "")).upper().strip()

    depart = str(q.get("departDate", "")).strip()
    ret = str(q.get("returnDate") or "").strip()

    adults = max(1, int(q.get("adults", 1)))
    children = max(0, int(q.get("children", 0)))
    infants = max(0, int(q.get("infants", 0)))

    legs = [
        FlightSegment(
            departure_airport=[
                [airport_enum(from_code), 0]
            ],
            arrival_airport=[
                [airport_enum(to_code), 0]
            ],
            travel_date=depart,
        )
    ]

    trip_type = (
        TripType.ROUND_TRIP
        if ret
        else TripType.ONE_WAY
    )

    if ret:
        legs.append(
            FlightSegment(
                departure_airport=[
                    [airport_enum(to_code), 0]
                ],
                arrival_airport=[
                    [airport_enum(from_code), 0]
                ],
                travel_date=ret,
            )
        )

    return FlightSearchFilters(
        trip_type=trip_type,

        passenger_info=PassengerInfo(
            adults=adults,
            children=children,
            infants_in_seat=0,
            infants_on_lap=infants,
        ),

        flight_segments=legs,

        seat_type=cabin_enum(
            q.get("cabin", "economy")
        ),

        stops=MaxStops.ANY,

        sort_by=SortBy.CHEAPEST,

        show_all_results=True,
    )


def search_google(q):
    filters = build_filters(q)

    searcher = SearchFlights()

    results = searcher.search(
        filters,
        top_n=MAX_RESULTS,
        currency="EGP",
    ) or []

    return results


class Handler(BaseHTTPRequestHandler):

    # =========================
    # CORS
    # =========================

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
            "Content-Type, x-api-key"
        )

    def _send(self, code, payload):
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            default=jsonable,
        ).encode("utf-8")

        self.send_response(code)

        self._cors()

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(raw)),
        )

        self.end_headers()

        self.wfile.write(raw)

    def _authorized(self):
        if not API_KEY:
            return True

        supplied = self.headers.get(
            "x-api-key",
            ""
        ).strip()

        return supplied == API_KEY

    def do_OPTIONS(self):
        self.send_response(204)

        self._cors()

        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/health":

            self._send(
                200,
                {
                    "ok": True,
                    "service": "jawwak-google-flights-fli",
                    "engine": "fli",
                    "roundTripEngine": "direct-google-rpc",
                    "apiKeyRequired": bool(API_KEY),
                },
            )

            return

        self._send(
            404,
            {
                "ok": False,
                "error": "Not found",
            },
        )

    def do_POST(self):
        path = urlparse(self.path).path

        if path != "/api/search-flights":

            self._send(
                404,
                {
                    "ok": False,
                    "error": "Not found",
                },
            )

            return

        if not self._authorized():

            self._send(
                401,
                {
                    "ok": False,
                    "error": "Unauthorized",
                },
            )

            return

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            body = self.rfile.read(length)

            q = json.loads(
                body.decode("utf-8") or "{}"
            )

            required = [
                "from",
                "to",
                "departDate",
            ]

            missing = [
                k
                for k in required
                if not q.get(k)
            ]

            if missing:
                raise ValueError(
                    "Missing required fields: "
                    + ", ".join(missing)
                )

            results = search_google(q)

            flights = [
                jsonable(x)
                for x in results
            ]

            is_round_trip = bool(
                q.get("returnDate")
            )

            self._send(
                200,
                {
                    "ok": True,

                    "count": len(flights),

                    "currency": "EGP",

                    "cached": False,

                    "source": "googleflights",

                    "engine": "fli",

                    "tripType": (
                        "round-trip"
                        if is_round_trip
                        else "one-way"
                    ),

                    "pricePolicy": (
                        "Price is taken from the same "
                        "fli Google Flights itinerary; "
                        "no separate return search or "
                        "manual price summation is used."
                    ),

                    "flights": flights,
                },
            )

        except Exception as exc:

            traceback.print_exc()

            self._send(
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "type": type(exc).__name__,
                },
            )


if __name__ == "__main__":

    print(
        f"Jawwak Google Flights fli server "
        f"listening on port {PORT}"
    )

    ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    ).serve_forever()