import express from "express";
import cors from "cors";
import { createQuery, Passengers, getFlights, fetchFlightsHtml, parse } from "fast-flights-ts";

const app = express();
app.use(cors());
app.use(express.json({ limit: "64kb" }));

const PORT = Number(process.env.PORT || 3000);
const API_KEY = process.env.JAWAKK_GOOGLE_FLIGHTS_API_KEY || "";
const REQUEST_TIMEOUT_MS = 25000;
const MIN_INTERVAL_MS = 1500;
let lastGoogleRequestAt = 0;
let activeGoogleRequest = null;

const sleep = ms => new Promise(r => setTimeout(r, ms));
const s = v => String(v ?? "").trim();
function date(v, name) {
  const x = s(v);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(x)) throw new Error(`${name} must be YYYY-MM-DD`);
  return x;
}
function cabin(v) {
  const x = s(v).toLowerCase();
  return ["premium-economy", "business", "first"].includes(x) ? x : "economy";
}
function auth(req) { return !API_KEY || (req.get("x-api-key") || "") === API_KEY; }
async function rateLimit() {
  const wait = MIN_INTERVAL_MS - (Date.now() - lastGoogleRequestAt);
  if (wait > 0) await sleep(wait);
  lastGoogleRequestAt = Date.now();
}
async function timeout(factory, ms) {
  let timer;
  try {
    return await Promise.race([
      factory(),
      new Promise((_, reject) => timer = setTimeout(() => reject(new Error("Google Flights request timed out")), ms))
    ]);
  } finally { clearTimeout(timer); }
}

function makeQuery(q, trip = "round-trip") {
  const flights = [{ date: q.departDate, from_airport: q.from, to_airport: q.to }];
  if (q.returnDate) flights.push({ date: q.returnDate, from_airport: q.to, to_airport: q.from });
  return createQuery({
    flights,
    seat: q.cabin,
    trip,
    passengers: new Passengers({
      adults: q.adults,
      children: q.children,
      infants_on_lap: q.infants
    }),
    currency: "EGP"
  });
}

function validateBody(body) {
  const q = {
    from: s(body?.from).toUpperCase(),
    to: s(body?.to).toUpperCase(),
    departDate: date(body?.departDate, "departDate"),
    returnDate: body?.returnDate ? date(body.returnDate, "returnDate") : null,
    adults: Math.max(1, Number(body?.adults) || 1),
    children: Math.max(0, Number(body?.children) || 0),
    infants: Math.max(0, Number(body?.infants) || 0),
    cabin: cabin(body?.cabin)
  };
  if (!q.from || !q.to) throw new Error("from and to are required");
  if (!q.returnDate) throw new Error("returnDate is required for this debug endpoint");
  return q;
}

function simplifySegment(x) {
  return {
    from: x?.from_airport?.code || x?.from?.code || x?.from || "",
    to: x?.to_airport?.code || x?.to?.code || x?.to || "",
    fromName: x?.from_airport?.name || x?.from?.name || "",
    toName: x?.to_airport?.name || x?.to?.name || "",
    departure: x?.departure?.dateTime || x?.departure?.datetime || x?.departure || null,
    arrival: x?.arrival?.dateTime || x?.arrival?.datetime || x?.arrival || null,
    duration: x?.duration ?? null,
    flightNumber: x?.flight_number || x?.flightNumber || x?.number || "",
    airline: x?.airline || x?.airline_name || x?.carrier || ""
  };
}

function summarize(raw, limit = 20) {
  const arr = Array.isArray(raw) ? raw : [];
  return arr.slice(0, limit).map((f, i) => {
    const segs = Array.isArray(f?.flights) ? f.flights : [];
    return {
      index: i,
      topLevelKeys: Object.keys(f || {}),
      price: f?.price ?? null,
      currency: f?.currency ?? null,
      airlines: f?.airlines ?? null,
      flightCount: segs.length,
      flights: segs.map(simplifySegment),
      hasReturnDirection: segs.some(x =>
        String(x?.from_airport?.code || "").toUpperCase() === "JED" &&
        String(x?.to_airport?.code || "").toUpperCase() === "CAI"
      )
    };
  });
}

async function getRoundTripRaw(q) {
  await rateLimit();
  const query = makeQuery(q, "round-trip");
  try {
    const raw = await timeout(() => getFlights(query, {
      timeout: REQUEST_TIMEOUT_MS,
      maxRetries: 1,
      retryDelay: 1500
    }), REQUEST_TIMEOUT_MS + 3000);
    return { raw, method: "rpc" };
  } catch (rpcErr) {
    console.warn("RPC failed; HTML fallback:", rpcErr?.message || rpcErr);
    const html = await timeout(() => fetchFlightsHtml(query, {
      timeout: REQUEST_TIMEOUT_MS,
      maxRetries: 1,
      retryDelay: 1500
    }), REQUEST_TIMEOUT_MS + 3000);
    return { raw: parse(html), method: "html", rpcError: rpcErr?.message || String(rpcErr) };
  }
}

app.get("/api/health", (req, res) => res.json({
  ok: true,
  service: "jawwak-google-flights-debug",
  engine: "fast-flights-ts",
  apiKeyRequired: Boolean(API_KEY),
  timestamp: new Date().toISOString()
}));

app.post("/api/debug-roundtrip", async (req, res) => {
  if (!auth(req)) return res.status(401).json({ ok: false, error: "Unauthorized" });
  if (activeGoogleRequest) await activeGoogleRequest;

  activeGoogleRequest = (async () => {
    try {
      const q = validateBody(req.body);
      const started = Date.now();
      const result = await getRoundTripRaw(q);
      const raw = Array.isArray(result.raw) ? result.raw : [];
      const sample = raw.slice(0, 3);
      const firstRawKeys = raw[0] ? Object.keys(raw[0]) : [];

      return res.json({
        ok: true,
        mode: "debug-roundtrip",
        request: q,
        method: result.method,
        elapsedMs: Date.now() - started,
        rawResultCount: raw.length,
        firstRawKeys,
        summary: summarize(raw, 20),
        rawSample: sample,
        note: "This endpoint intentionally returns the parsed Google Flights round-trip result before Jawwak mapping. It is diagnostic only and must not be connected to the main site."
      });
    } catch (err) {
      return res.status(502).json({ ok: false, error: err?.message || String(err) });
    }
  })();

  try { await activeGoogleRequest; }
  finally { activeGoogleRequest = null; }
});

app.listen(PORT, () => console.log(`Jawwak Google Flights DEBUG server listening on port ${PORT}`));
