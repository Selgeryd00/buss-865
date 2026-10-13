"""Buss 865 vid Berg vägskäl. Data: Trafiklab.se (CC BY 4.0)."""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
STATE_FILE = Path("state.json")
BASE = "https://realtime-api.trafiklab.se/v1"
STOP_NAME = "Berg vägskäl"
LINE = "865"

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "buss-865/2.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.load(res)

def api(path, key):
    return get_json(BASE + path + "?key=" + urllib.parse.quote(key, safe=""))

def send(topic, title, message):
    if not topic or "/" in topic or "?" in topic:
        raise RuntimeError("Ogiltigt eller saknat NTFY_TOPIC")
    req = urllib.request.Request(
        "https://ntfy.sh/" + urllib.parse.quote(topic, safe=""),
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "bus"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        print("Notis skickad:", response.status)

def find_stop(key):
    results = api("/stops/name/" + urllib.parse.quote(STOP_NAME, safe=""), key)
    groups = results.get("stop_groups", [])
    exact = [x for x in groups if x.get("name", "").casefold() == STOP_NAME.casefold()
             and x.get("area_type") == "RIKSHALLPLATS"]
    if len(exact) != 1:
        print("Hållplatssökning:", [(x.get("name"), x.get("id")) for x in groups[:15]])
        raise RuntimeError("Kan inte identifiera Berg vägskäl entydigt")
    return str(exact[0]["id"])

def local_time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)

def main():
    topic = os.getenv("NTFY_TOPIC", "")
    if os.getenv("TEST_NOTIFICATION") == "true":
        send(topic, "Test - buss 865", "Testnotis från GitHub. Bevakaren kan nå ntfy.")
        return
    now = dt.datetime.now(TZ)
    # Include 04:50 for departures just after 05:00.
    if now.weekday() >= 5 or not ((now.hour == 4 and now.minute >= 50) or now.hour == 5):
        print("Utanför bevakningstid:", now.isoformat())
        return
    key = os.getenv("TRAFIKLAB_API_KEY", "")
    if not key:
        raise RuntimeError("GitHub secret BUSS865NYCKEL saknas")
    area = find_stop(key)
    board = api("/departures/" + urllib.parse.quote(area, safe=""), key)
    direction_filter = "uppsala"
    entries = []
    for dep in board.get("departures", []):
        route = dep.get("route") or {}
        if str(route.get("designation", "")).strip() != LINE:
            continue
        direction = route.get("direction") or (route.get("destination") or {}).get("name") or "okänd riktning"
        destination = (route.get("destination") or {}).get("name") or ""
        if direction_filter not in (direction + " " + destination).casefold():
            continue
        when = dep.get("realtime") or dep.get("scheduled")
        if not when:
            continue
        eta = local_time(when)
        mins = (eta - now).total_seconds() / 60
        if -1 <= mins <= 20:
            trip = dep.get("trip") or {}
            ident = str(trip.get("trip_id") or dep.get("scheduled")) + ":" + str(trip.get("start_date") or now.date())
            entries.append((eta, mins, ident, direction, dep))
    entries.sort(key=lambda x: x[0])
    print("Hållplats-ID:", area, "Linje 865-avgångar:", len(entries))
    if not entries:
        return
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    if state.get("date") != str(now.date()):
        state = {"date": str(now.date()), "sent": []}
    sent = set(state["sent"])
    for eta, mins, ident, direction, dep in entries:
        for threshold in (10, 5):
            flag = ident + ":" + str(threshold)
            # 5-minute cron may be delayed; allow a modest late margin.
            if flag in sent or not (0 <= mins <= threshold and mins > threshold - 5.5):
                continue
            canceled = dep.get("canceled", False)
            real = dep.get("is_realtime", False)
            status = "INSTÄLLD" if canceled else ("realtidsprognos" if real else "tidtabellstid")
            message = (f"Linje {LINE} mot {direction}, Berg vägskäl: "
                       f"{'inställd avgång' if canceled else 'ca ' + str(round(mins)) + ' min kvar'} "
                       f"(kl {eta:%H:%M}; {status}). Källa: Trafiklab.se")
            send(topic, "Buss 865 - " + str(threshold) + " min", message)
            sent.add(flag)
    state["sent"] = sorted(sent)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")

if __name__ == "__main__":
    main()
