"""Build week-19/lab.ipynb — Real-time GIS via WebSockets + streaming TLEs."""
import json
from pathlib import Path
def md(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"markdown","metadata":{},"source":L}
def code(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":L}
cells=[]
cells.append(md(
"""# Week 19: Real-time GIS — WebSockets + streaming satellite positions

**Track:** Mission GIS Engineer (Advanced)
**Full primer + quiz:** [https://launchdetect.com/academy/week/19/](https://launchdetect.com/academy/week/19/)

---

_Map your launch detection live, your fleet of trackers needs WebSocket. HTTP polling at 1 Hz wastes 70% of the bandwidth on TCP overhead. WebSocket holds a single TCP connection open, multiplexes frames, and lets the server push updates the instant they're ready — exactly the pattern LaunchDetect's STM dashboard uses. This week implements a tiny WebSocket SERVER that propagates the ISS every second + a CLIENT that consumes positions, in the same notebook using `asyncio`. Then replaces the random-data placeholder with real skyfield propagation._
"""))

cells.append(md("""## Why this week matters

LaunchDetect's STM dashboard pushes detection events to ~thousands of connected clients in real time. Every connection that's not a WebSocket is wasting roundtrip cost. The protocol is simple — HTTP upgrade handshake, then binary or text frames in either direction — but the API conventions matter."""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q websockets nest_asyncio skyfield requests"""))

cells.append(md(
"""## Step 1 — Implement a WebSocket server that streams ISS positions

The pattern: connect → server pushes one JSON frame per second with `{t_utc, lat, lon, alt_km}`. We use the `websockets` library (the same one Django Channels and FastAPI built on top of).
"""))
cells.append(code(
"""import asyncio, json, datetime
from skyfield.api import EarthSatellite, load, wgs84
import websockets, nest_asyncio
nest_asyncio.apply()

# Embedded ISS TLE for offline / fast-test (Week 7's; replace via live fetch upstream)
ISS_L1='1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993'
ISS_L2='2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361'
ts = load.timescale()
sat = EarthSatellite(ISS_L1, ISS_L2, 'ISS', ts)

async def iss_stream_handler(websocket):
    print('  [server] client connected')
    for _ in range(5):  # send 5 frames then close (lab keeps it short)
        t = ts.now()
        sub = wgs84.subpoint_of(sat.at(t))
        alt = wgs84.height_of(sat.at(t)).km
        msg = {
            't_utc': datetime.datetime.utcnow().isoformat() + 'Z',
            'lat': float(sub.latitude.degrees),
            'lon': float(sub.longitude.degrees),
            'alt_km': float(alt),
        }
        await websocket.send(json.dumps(msg))
        await asyncio.sleep(1)
    print('  [server] sent 5 frames, closing')

print('Server handler defined.')"""))

cells.append(md("""## Step 2 — A client that consumes 5 frames + the server runs in parallel"""))
cells.append(code(
"""async def client():
    uri = 'ws://localhost:8765'
    print('  [client] connecting…')
    async with websockets.connect(uri) as ws:
        for _ in range(5):
            raw = await ws.recv()
            msg = json.loads(raw)
            print(f\"  [client] {msg['t_utc']}  lat={msg['lat']:+7.3f}  lon={msg['lon']:+8.3f}  alt={msg['alt_km']:.1f} km\")

async def run_demo():
    # Start server, wait briefly for socket bind, run client
    server = await websockets.serve(iss_stream_handler, 'localhost', 8765)
    print('[server] listening on ws://localhost:8765')
    await asyncio.sleep(0.5)
    await client()
    server.close()
    await server.wait_closed()
    print('[demo] complete')

asyncio.run(run_demo())"""))

cells.append(md("""## Step 3 — Same pattern, scaled up: a fleet of 100 sats streaming

In production the server doesn't propagate one sat per frame — it broadcasts the same precomputed batch to every connected client. We demo the broadcast pattern: 100 client-position frames in one message every second."""))
cells.append(code(
"""async def fleet_handler(websocket):
    # Build 100 sats once
    import random, math
    rng = random.Random(0)
    base_lon = -180
    for tick in range(3):
        fleet = []
        for i in range(100):
            # Synthetic sweep across longitudes
            fleet.append({
                'id': f'SAT-{i:03d}',
                'lat': 50 * math.sin(0.4 * (tick + i)),
                'lon': ((base_lon + (tick * 10 + i * 3.6) + 180) % 360) - 180,
                'alt_km': 400 + i * 5,
            })
        await websocket.send(json.dumps({'tick': tick, 'fleet': fleet}))
        await asyncio.sleep(1)

async def fleet_client():
    async with websockets.connect('ws://localhost:8766') as ws:
        for _ in range(3):
            msg = json.loads(await ws.recv())
            print(f\"  tick {msg['tick']}: {len(msg['fleet'])} sats, alt range \"
                  f\"{min(s['alt_km'] for s in msg['fleet']):.0f}–{max(s['alt_km'] for s in msg['fleet']):.0f} km\")

async def run_fleet():
    srv = await websockets.serve(fleet_handler, 'localhost', 8766)
    await asyncio.sleep(0.3)
    await fleet_client()
    srv.close(); await srv.wait_closed()

asyncio.run(run_fleet())"""))

cells.append(md(
"""## Common gotchas

- **WebSocket can't broadcast natively.** Out of the box, each connection is independent. To broadcast you keep a set of connected `WebSocketServerProtocol` objects and iterate. The `websockets.broadcast` helper does this for you.
- **Backpressure.** A slow client buffering 100k+ frames will OOM your server. Use `websockets.serve(..., max_queue=32)` or drop late frames.
- **`nest_asyncio.apply()` is a Colab/Jupyter hack** — IPython already runs an event loop; nesting another `asyncio.run` breaks without it. Don't use this in production code; use the existing loop instead.
- **Reconnects.** Production clients should reconnect on network blip + resume with a "last seen tick" replay. Naive `while True: connect()` floods the server on outages.
- **JSON vs binary.** For positional data 100s of bytes per frame, JSON is fine. For raw raster/dense numeric streams, pack into binary frames (MessagePack, Protobuf) to halve bandwidth.
"""))

cells.append(md(
"""## Self-check
- [ ] Server-client demo prints 5 ISS frames with lat/lon/alt.
- [ ] Each frame's altitude is in the 400-440 km ISS envelope.
- [ ] Fleet broadcast demo: 100 sats per frame, 3 frames.
- [ ] No errors on close — both servers shut down cleanly.
- [ ] Quiz on the [Week 19 page](https://launchdetect.com/academy/week/19/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-19/lab.ipynb ({len(cells)} cells)")
