import os, json, urllib.request, datetime, zoneinfo
from pathlib import Path

TZ=zoneinfo.ZoneInfo("Europe/Stockholm")
STATE=Path("state.json")
def request(url, token=None, data=None):
    headers={"User-Agent":"buss-865-monitor/1.0"}
    if token: headers["Authorization"]="Bearer "+token
    if data is not None: headers["Content-Type"]="application/json"
    req=urllib.request.Request(url,headers=headers,data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)

def main():
    now=datetime.datetime.now(TZ)
    if now.weekday()>4 or not (5<=now.hour<6):
        print("Utanför bevakningstid"); return
    url=os.environ.get("DEPARTURES_URL","")
    if not url: raise RuntimeError("DEPARTURES_URL saknas. Konfigurera verifierad realtids-API-URL.")
    data=request(url)
    # A verified adapter must supply a normalized list of arrivals with ISO times.
    arrivals=data.get("arrivals",[])
    line=os.environ.get("LINE","865")
    candidates=[x for x in arrivals if str(x.get("line"))==line and x.get("arrival_time")]
    if not candidates: print("Ingen verifierad ankomstprognos"); return
    candidates.sort(key=lambda x:x["arrival_time"])
    target=candidates[0]
    eta=datetime.datetime.fromisoformat(target["arrival_time"].replace("Z","+00:00")).astimezone(TZ)
    minutes=(eta-now).total_seconds()/60
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    trip=str(target.get("trip_id",eta.isoformat()))
    if state.get("trip")!=trip: state={"trip":trip,"sent":[]}
    message=None; flag=None
    if 0<=minutes<=5 and "5" not in state["sent"]: flag="5";message=f"Buss {line}: cirka {round(minutes)} minuter kvar till Berg vägskäl."
    elif 5<minutes<=10 and "10" not in state["sent"]: flag="10";message=f"Buss {line}: cirka {round(minutes)} minuter kvar till Berg vägskäl."
    if message:
        app=os.environ.get("NTFY_TOPIC","")
        if not app: raise RuntimeError("NTFY_TOPIC saknas")
        req=urllib.request.Request("https://ntfy.sh/"+app,data=message.encode(),headers={"Title":"Buss 865 - Berg vagkorsel","Tags":"bus","Priority":"high"},method="POST")
        with urllib.request.urlopen(req,timeout=15) as resp: print("Notis skickad",resp.status)
        state["sent"].append(flag)
    STATE.write_text(json.dumps(state))
if __name__=="__main__": main()
