import json, os, traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from swoop import search, price_selector

PORT = int(os.environ.get('PORT','10000'))
MAX_RESULTS = int(os.environ.get('MAX_RESULTS','30'))

def send_json(h, data, status=200):
    body=json.dumps(data,ensure_ascii=False,default=str).encode()
    h.send_response(status)
    h.send_header('Access-Control-Allow-Origin','*')
    h.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
    h.send_header('Access-Control-Allow-Headers','Content-Type, Accept')
    h.send_header('Content-Type','application/json; charset=utf-8')
    h.send_header('Content-Length',str(len(body)))
    h.end_headers(); h.wfile.write(body)

def val(o,n,d=None):
    try:return getattr(o,n,d)
    except:return d

def seg_json(s):
    return {'airline':val(s,'airline'),'flightNumber':val(s,'flight_number'),'aircraft':val(s,'aircraft'),'origin':val(s,'origin'),'destination':val(s,'destination'),'departureTime':val(s,'departure_time'),'arrivalTime':val(s,'arrival_time'),'legroom':val(s,'legroom'),'co2Grams':val(s,'co2_grams'),'amenities':val(s,'amenities')}

def itin_json(i):
    if i is None:return None
    return {'price':val(i,'price'),'airlineNames':val(i,'airline_names',[]),'stopCount':val(i,'stop_count'),'travelTime':val(i,'travel_time'),'bookingToken':val(i,'booking_token'),'segments':[seg_json(x) for x in (val(i,'flights',[]) or [])],'layovers':[{'minutes':val(x,'minutes'),'origin':val(x,'origin'),'destination':val(x,'destination'),'isOvernight':val(x,'is_overnight')} for x in (val(i,'layovers',[]) or [])]}

def option_json(o):
    return {'selector':val(o,'selector'),'price':val(o,'price'),'currency':val(o,'currency'),'legs':[{'origin':val(l,'origin'),'destination':val(l,'destination'),'date':val(l,'date'),'itinerary':itin_json(val(l,'itinerary'))} for l in (val(o,'legs',[]) or [])]}

def jint(v,d=0):
    try:return int(v)
    except:return d

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):print('[HTTP]',fmt%args,flush=True)
    def do_OPTIONS(self):send_json(self,{'ok':True},204)
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':
            send_json(self,{'ok':True,'service':'jawwak-google-flights-swoop','engine':'swoop','apiKeyRequired':False}); return
        send_json(self,{'ok':False,'error':'Not Found'},404)
    def body(self):
        n=jint(self.headers.get('Content-Length'),0); return json.loads(self.rfile.read(n).decode())
    def do_POST(self):
        p=urlparse(self.path).path
        if p=='/api/search-flights':return self.search_flights()
        if p=='/api/price-selector':return self.price_selected()
        send_json(self,{'ok':False,'error':'Not Found'},404)
    def search_flights(self):
        try:
            r=self.body(); origin=str(r.get('from','')).strip().upper(); dest=str(r.get('to','')).strip().upper(); date=str(r.get('departDate','')).strip(); ret=r.get('returnDate') or None
            if not origin or not dest or not date:return send_json(self,{'ok':False,'error':'from, to and departDate are required'},400)
            kw={'cabin':str(r.get('cabin','economy')).lower(),'adults':jint(r.get('adults'),1),'children':jint(r.get('children'),0),'infants_in_seat':jint(r.get('infantsInSeat'),0),'infants_on_lap':jint(r.get('infants'),0),'timeout':90,'retries':2,'country':'EG'}
            if r.get('maxStops') is not None:kw['max_stops']=jint(r.get('maxStops'))
            if r.get('airlines'):
                a=r['airlines']; kw['airlines']=[x.strip().upper() for x in a.split(',')] if isinstance(a,str) else a
            t=datetime.utcnow(); result = search(     origin,     dest,     date,     return_date=ret,     cabin=kw.get("cabin", "economy"),     timeout=90,     retries=2,     country="EG", ); elapsed=(datetime.utcnow()-t).total_seconds()
            opts=(val(result,'results',[]) or [])[:MAX_RESULTS]
            pr=val(result,'price_range')
            send_json(self,{'ok':True,'count':len(opts),'currency':val(result,'currency') or 'EGP','source':'googleflights','engine':'swoop','tripType':'round-trip' if ret else 'one-way','from':origin,'to':dest,'departDate':date,'returnDate':ret,'elapsedSeconds':elapsed,'isComplete':val(result,'is_complete'),'priceRange':{'minimum':val(pr,'minimum'),'maximum':val(pr,'maximum')} if pr else None,'flights':[option_json(x) for x in opts],'pricePolicy':'Google Flights shopping total; selected results can be price-checked with /api/price-selector.'})
        except Exception as e:
            print(traceback.format_exc(),flush=True); send_json(self,{'ok':False,'engine':'swoop','error':str(e),'exceptionType':str(type(e)),'traceback':traceback.format_exc()},500)
    def price_selected(self):
        try:
            r=self.body(); selector=str(r.get('selector','')).strip()
            if not selector:return send_json(self,{'ok':False,'error':'selector is required'},400)
            t=datetime.utcnow(); result=price_selector(selector,timeout=90,retries=2,country='EG'); elapsed=(datetime.utcnow()-t).total_seconds()
            if result is None:return send_json(self,{'ok':True,'found':False,'engine':'swoop','elapsedSeconds':elapsed})
            opts=val(result,'booking_options',[]) or []
            send_json(self,{'ok':True,'found':True,'engine':'swoop','elapsedSeconds':elapsed,'price':val(result,'price'),'currency':val(result,'currency') or 'EGP','fareBrand':val(result,'fare_brand'),'isEstimate':val(result,'is_estimate'),'bookingOptions':[{'price':val(x,'price'),'currency':val(x,'currency'),'brandLabel':val(x,'brand_label'),'fareFamily':val(x,'fare_family'),'sellerName':val(x,'seller_name'),'sellerCode':val(x,'seller_code'),'bookingUrl':val(x,'booking_url'),'isAirlineDirect':val(x,'is_airline_direct')} for x in opts]})
        except Exception as e:
            print(traceback.format_exc(),flush=True); send_json(self,{'ok':False,'engine':'swoop','error':str(e),'exceptionType':str(type(e)),'traceback':traceback.format_exc()},500)

if __name__=='__main__':
    print('Jawwak Google Flights - Swoop',flush=True); print(f'Port: {PORT}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
