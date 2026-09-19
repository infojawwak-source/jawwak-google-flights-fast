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


def cors(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, OPTIONS"
    )
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type, Accept"
    )


def send_json(handler, status, data):

    body = json.dumps(
        data,
        ensure_ascii=False,
        default=str
    ).encode("utf-8")

    handler.send_response(status)
    cors(handler)

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

    length = int(
        handler.headers.get(
            "Content-Length",
            "0"
        )
    )

    if length <= 0:
        return {}

    return json.loads(
        handler.rfile.read(length).decode("utf-8")
    )


def airport(code):

    return getattr(
        Airport,
        str(code).upper()
    )


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):

        self.send_response(204)
        cors(self)
        self.end_headers()


    def do_GET(self):

        path = self.path.split("?")[0]

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
                        "0.9.0"
                }
            )

            return

        send_json(
            self,
            404,
            {
                "ok": False,
                "error": "Not Found"
            }
        )


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

            data = read_json(self)

            from_code = data.get(
                "from",
                "CAI"
            )

            to_code = data.get(
                "to",
                "JED"
            )

            depart_date = data.get(
                "departDate",
                "2026-10-19"
            )

            print(
                "======================================"
            )

            print(
                "TEST FLI SEARCH"
            )

            print(
                "FROM:",
                from_code
            )

            print(
                "TO:",
                to_code
            )

            print(
                "DATE:",
                depart_date
            )

            print(
                "======================================"
            )


            # ------------------------------------------
            # PASSENGERS
            # ------------------------------------------

            passengers = PassengerInfo(
                adults=1,
                children=0,
                infants_on_lap=0,
                infants_in_seat=0
            )


            # ------------------------------------------
            # SEGMENT
            # ------------------------------------------

            segment = FlightSegment(

                departure_airport=[
                    [
                        airport(from_code),
                        0
                    ]
                ],

                arrival_airport=[
                    [
                        airport(to_code),
                        0
                    ]
                ],

                travel_date=depart_date
            )


            # ------------------------------------------
            # FILTERS
            # ------------------------------------------

            filters = FlightSearchFilters(

                passenger_info=passengers,

                flight_segments=[
                    segment
                ],

                stops=MaxStops.ANY,

                seat_type=SeatType.ECONOMY,

                sort_by=SortBy.CHEAPEST,

                show_all_results=True
            )


            print(
                "FILTERS CREATED"
            )

            print(
                repr(filters)
            )


            # ------------------------------------------
            # SEARCH
            # ------------------------------------------

            engine = SearchFlights()

            print(
                "SEARCH ENGINE CREATED"
            )

            results = engine.search(
                filters,
                top_n=5
            )


            print(
                "RAW RESULTS TYPE:",
                type(results)
            )

            print(
                "RAW RESULTS:",
                repr(results)
            )


            if results is None:

                results = []


            output = []


            for item in results:

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

                        value = str(item)

                    output.append(value)

                except Exception as e:

                    print(
                        "SERIALIZATION ERROR:",
                        e
                    )


            send_json(
                self,
                200,
                {
                    "ok": True,

                    "resultCount":
                        len(output),

                    "rawResultType":
                        str(type(results)),

                    "results":
                        output
                }
            )


        except Exception as e:

            print(
                "======================================"
            )

            print(
                "ERROR:",
                str(e)
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
                    "error": str(e)
                }
            )


def main():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    print(
        f"Server running on port {PORT}"
    )

    server.serve_forever()


if __name__ == "__main__":
    main()