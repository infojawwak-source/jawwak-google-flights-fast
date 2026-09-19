import express from "express";
import cors from "cors";
import { createQuery, Passengers, getFlights, fetchFlightsHtml, parse } from "fast-flights-ts";

const app = express();
app.use(cors());
app.use(express.json({ limit: "64kb" }));

const PORT = Number(process.env.PORT || 3000);
const API_KEY = process.env.JAWAKK_GOOGLE_FLIGHTS_API_KEY || "";
const REQUEST_TIMEOUT_MS = 25000;
const CACHE_TTL_MS = 5 * 60 * 1000;
const MIN_INTERVAL_MS = 1500;
const MAX_RESULTS = 50;

const cache = new Map();
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
  return ["premium-economy","business","first"].includes(x) ? x : "economy";
}
function key(x) {
  return JSON.stringify(x);
}
function auth(req) {
  return !API_KEY || (req.get("x-api-key") || "") === API_KEY;
}
function cleanCache() {
  const now = Date.now();
  for (const [k,v] of cache) if (v.expiresAt <= now) cache.delete(k);
}
async function rateLimit() {
  const wait = MIN_INTERVAL_MS - (Date.now() - lastGoogleRequestAt);
  if (wait > 0) await sleep(wait);
  lastGoogleRequestAt = Date.now();
}
async function timeout(promiseFactory, ms) {
  let timer;
  try {
    return await Promise.race([
      promiseFactory(),
      new Promise((_, reject) => timer = setTimeout(() => reject(new Error("Google Flights request timed out")), ms))
    ]);
  } finally { clearTimeout(timer); }
}

function buildQuery(q) {
  const flights = [{ date:q.departDate, from_airport:q.from, to_airport:q.to }];
  if (q.returnDate) flights.push({ date:q.returnDate, from_airport:q.to, to_airport:q.from });

  // fast-flights-ts exposes round-trip results as outbound choices first.
  // It does not expose Google's departure_token in its typed result.
  // For a two-leg customer round trip, use Google's multi-city query shape
  // so the two legs are returned inside the SAME itinerary and the price is
  // the price attached to that complete two-leg itinerary.
  const trip = q.returnDate ? "multi-city" : "one-way";

  return createQuery({
    flights,
    seat:q.cabin,
    trip,
    passengers:new Passengers({adults:q.adults, children:q.children, infants_on_lap:q.infants}),
    currency:"EGP"
  });
}

function mapFlight(f, i, q) {
  const segs = Array.isArray(f?.flights) ? f.flights : [];
  if (!segs.length) return null;

  const price = Number(f?.price);
  if (!Number.isFinite(price) || price <= 0) return null;

  const airlines = Array.isArray(f.airlines) ? f.airlines : [];
  const legs = segs.map(x => ({
    from:x?.from_airport?.code || "",
    to:x?.to_airport?.code || "",
    fromName:x?.from_airport?.name || "",
    toName:x?.to_airport?.name || "",
    depTime:x?.departure?.dateTime || x?.departure?.datetime || x?.departure || null,
    arrTime:x?.arrival?.dateTime || x?.arrival?.datetime || x?.arrival || null,
    durationMinutes:Number(x?.duration) || 0,
    aircraft:x?.plane_type || null
  }));

  // Round-trip results must contain both directions in the SAME Google
  // itinerary. We never attach a separately searched return flight because
  // that could create a combination whose displayed price does not belong
  // to the paired itinerary.
  let outboundLegs = legs;
  let returnLegs = [];

  if (q?.returnDate) {
    const destination = String(q.to || "").toUpperCase();
    const splitIndex = legs.findIndex((x, idx) =>
      idx < legs.length - 1 && String(x.to || "").toUpperCase() === destination
    );

    if (splitIndex >= 0) {
      outboundLegs = legs.slice(0, splitIndex + 1);
      returnLegs = legs.slice(splitIndex + 1);
    }
  }

  if (q?.returnDate) {
    const hasValidReturn =
      returnLegs.length > 0 &&
      String(returnLegs[0]?.from || "").toUpperCase() === String(q.to || "").toUpperCase() &&
      String(returnLegs[returnLegs.length - 1]?.to || "").toUpperCase() === String(q.from || "").toUpperCase();

    if (!hasValidReturn) return null;
  }

  const outboundDurationMinutes = outboundLegs.reduce((n,x)=>n+x.durationMinutes,0);
  const inboundDurationMinutes = returnLegs.reduce((n,x)=>n+x.durationMinutes,0);
  const outboundFirst = outboundLegs[0];
  const outboundLast = outboundLegs[outboundLegs.length-1];
  const inboundFirst = returnLegs[0];
  const inboundLast = returnLegs[returnLegs.length-1];

  return {
    id:`gfl_${Date.now()}_${i}_${Math.random().toString(36).slice(2,8)}`,
    source:"googleflights",
    airlineName:airlines[0] || "شركة طيران",
    airlineCode:"",
    airlines,
    flightNumber:"",
    from:outboundFirst?.from || q?.from || "",
    to:outboundLast?.to || q?.to || "",
    depTime:outboundFirst?.depTime || null,
    arrTime:outboundLast?.arrTime || null,
    durationMinutes:outboundDurationMinutes,
    duration:`${outboundDurationMinutes} دقيقة`,
    stops:Math.max(0,outboundLegs.length-1),
    price:Math.round(price),
    currency:"EGP",
    originalPrice:Math.round(price),
    originalCurrency:"EGP",
    priceType:q?.returnDate ? "google-two-leg-itinerary-total" : "google-one-way",
    legs:outboundLegs,
    returnLeg:returnLegs.length ? {
      from:inboundFirst?.from || q?.to || "",
      to:inboundLast?.to || q?.from || "",
      depTime:inboundFirst?.depTime || null,
      arrTime:inboundLast?.arrTime || null,
      durationMinutes:inboundDurationMinutes,
      duration:`${inboundDurationMinutes} دقيقة`,
      stops:Math.max(0,returnLegs.length-1),
      flightNumber:"",
      legs:returnLegs
    } : null,
    bookingAvailable:false,
    bookingToken:null,
    carbon:f?.carbon || null
  };
}

async function search(q) {
  cleanCache();
  const k = key(q);
  const cached = cache.get(k);
  if (cached && cached.expiresAt > Date.now()) return {...cached.data, cached:true};

  if (activeGoogleRequest) await activeGoogleRequest;

  activeGoogleRequest = (async()=>{
    // Primary request: for round trips use a two-leg Google itinerary so the
    // returned price belongs to the same result as both legs. This avoids
    // separately pairing a return flight with an outbound price.
    await rateLimit();
    const query = buildQuery(q);
    let raw;

    try {
      raw = await timeout(
        () => getFlights(query, {
          timeout: REQUEST_TIMEOUT_MS,
          maxRetries: 1,
          retryDelay: 1500
        }),
        REQUEST_TIMEOUT_MS + 3000
      );
    } catch (rpcErr) {
      console.warn(
        "Google Flights RPC failed; trying HTML fallback:",
        rpcErr?.message || rpcErr
      );

      const html = await timeout(
        () => fetchFlightsHtml(query, {
          timeout: REQUEST_TIMEOUT_MS,
          maxRetries: 1,
          retryDelay: 1500
        }),
        REQUEST_TIMEOUT_MS + 3000
      );

      raw = parse(html);
    }

    const results = Array.isArray(raw) ? raw : [];
    let flights = results
      .map((flight, index) => mapFlight(flight, index, q))
      .filter(Boolean)
      .sort((a,b)=>a.price-b.price)
      .slice(0,MAX_RESULTS);

    // IMPORTANT:
    // For round trips, only use an itinerary that already contains both
    // outbound and return legs from the SAME Google result. We intentionally
    // do NOT run a separate return search and attach it by airline.
    //
    // This prevents a return flight from one itinerary being paired with the
    // price of another itinerary.
    if (q.returnDate) {
      flights = flights
        .filter(f => f.returnLeg)
        .sort((a,b) => a.price - b.price)
        .slice(0, MAX_RESULTS);
    }

    const data = {
      ok:true,
      count:flights.length,
      currency:"EGP",
      cached:false,
      source:"googleflights",
      tripType:q.returnDate ? "round-trip" : "one-way",
      flights,
      pricePolicy: q.returnDate
        ? "Two-leg round-trip prices are accepted only when Google returns both legs in the same itinerary; no separate return-leg pairing is used."
        : "One-way price from Google Flights."
    };

    cache.set(k,{expiresAt:Date.now()+CACHE_TTL_MS,data});
    return data;
  })();

  try { return await activeGoogleRequest; }
  finally { activeGoogleRequest = null; }
}

app.get("/api/health",(req,res)=>res.json({
  ok:true,
  service:"jawwak-google-flights",
  engine:"fast-flights-ts",
  apiKeyRequired:Boolean(API_KEY),
  cacheEntries:cache.size,
  timestamp:new Date().toISOString()
}));

app.post("/api/search-flights",async(req,res)=>{
  if(!auth(req)) return res.status(401).json({ok:false,error:"Unauthorized"});
  try {
    const b=req.body||{};
    const q={
      from:s(b.from).toUpperCase(),
      to:s(b.to).toUpperCase(),
      departDate:date(b.departDate,"departDate"),
      returnDate:b.returnDate ? date(b.returnDate,"returnDate") : null,
      adults:Math.max(1,Math.min(9,Number(b.adults)||1)),
      children:Math.max(0,Math.min(8,Number(b.children)||0)),
      infants:Math.max(0,Math.min(8,Number(b.infants)||0)),
      cabin:cabin(b.cabin)
    };
    if(!q.from||!q.to) return res.status(400).json({ok:false,error:"from and to are required"});
    if(q.from===q.to) return res.status(400).json({ok:false,error:"from and to must be different"});
    if(q.returnDate && q.returnDate<q.departDate) return res.status(400).json({ok:false,error:"returnDate must be on or after departDate"});
    return res.json(await search(q));
  } catch(err) {
    console.error("Google Flights search failed:",err?.stack||err);
    const blocked=/captcha|blocked|consent/i.test(err?.message||"");
    return res.status(blocked?503:502).json({
      ok:false,source:"googleflights",
      error:blocked?"Google Flights blocked this request temporarily":"Google Flights search failed",
      detail:err?.message||String(err)
    });
  }
});

app.use((req,res)=>res.status(404).json({ok:false,error:"Not found"}));
app.listen(PORT,()=>console.log(`Jawwak Google Flights server listening on port ${PORT}`));
