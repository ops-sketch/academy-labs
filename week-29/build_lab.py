"""Build week-29/lab.ipynb — Geospatial APIs: FastAPI + DuckDB-spatial."""
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
"""# Week 29: Geospatial APIs — FastAPI + spatial SQL

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/29/](https://launchdetect.com/academy/week/29/)

---

_The capstone of all the previous spatial work: expose a database of launch pads (Week 6) as a **REST API** that returns GeoJSON, with a `/pads/near` endpoint that does spatial queries. Built on FastAPI + DuckDB-spatial in this notebook; the same code drops into a production PostgreSQL + PostGIS deployment by changing the connection string._
"""))

cells.append(md("""## Why this week matters

A real space-GIS service exposes spatial data via HTTP. Three patterns dominate:

1. **OGC API Features** — the modern standard (replaces WFS). REST, GeoJSON-native.
2. **OGC API Tiles** — vector tile endpoints with Z/X/Y query params.
3. **Custom REST** — when the OGC specs don't fit. Most production services live here.

We build a custom REST API since it's the most common pattern. FastAPI handles the HTTP + validation; DuckDB-spatial handles the SQL. In production swap DuckDB→PostGIS by changing one connection-string line."""))

cells.append(code("""!pip install -q fastapi uvicorn duckdb nest_asyncio httpx"""))

cells.append(md("""## Step 1 — Spin up DuckDB + load pads (re-using Week 6)"""))
cells.append(code(
"""import duckdb
con = duckdb.connect(':memory:')
con.execute('INSTALL spatial; LOAD spatial;')

PADS = [
    ('SLC-40 Cape',         28.5618,  -80.5772, 'SpaceX'),
    ('LC-39A',              28.6082,  -80.6041, 'SpaceX/NASA'),
    ('SLC-4E Vandenberg',   34.6321, -120.6106, 'SpaceX'),
    ('Mahia LC-1',         -39.2606,  177.8649, 'Rocket Lab'),
    ('Baikonur 1/5',        45.92,     63.3422, 'Roscosmos'),
    ('Wenchang LC-201',     19.614,   110.951,  'CASC'),
    ('Tanegashima Yoshinobu', 30.4,   130.97,   'JAXA'),
    ('Kourou ELA-4',         5.239,   -52.7689, 'Arianespace'),
]
con.execute('CREATE TABLE pads (id INTEGER, name TEXT, lat DOUBLE, lon DOUBLE, operator TEXT, geom GEOMETRY)')
for i, (n, la, lo, op) in enumerate(PADS):
    con.execute('INSERT INTO pads VALUES (?, ?, ?, ?, ?, ST_Point(?, ?))', [i+1, n, la, lo, op, lo, la])
print(f'Loaded {len(PADS)} pads into DuckDB-spatial.')"""))

cells.append(md("""## Step 2 — FastAPI app with three endpoints"""))
cells.append(code(
"""from fastapi import FastAPI, HTTPException, Query
from typing import Optional
import json

app = FastAPI(title='LaunchDetect Pads API', version='1.0',
              description='Demo geospatial REST API built on FastAPI + DuckDB-spatial.')

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/pads')
def list_pads(operator: Optional[str] = None, limit: int = 50):
    q = 'SELECT id, name, lat, lon, operator FROM pads'
    params = []
    if operator:
        q += ' WHERE operator = ?'; params.append(operator)
    q += ' LIMIT ?'; params.append(limit)
    rows = con.execute(q, params).fetchall()
    return {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r[3], r[2]]},
            'properties': {'id': r[0], 'name': r[1], 'operator': r[4]},
        } for r in rows],
    }

@app.get('/pads/{pad_id}')
def get_pad(pad_id: int):
    rows = con.execute('SELECT id, name, lat, lon, operator FROM pads WHERE id = ?', [pad_id]).fetchall()
    if not rows:
        raise HTTPException(404, 'pad not found')
    r = rows[0]
    return {
        'type':'Feature',
        'geometry':{'type':'Point','coordinates':[r[3], r[2]]},
        'properties':{'id':r[0],'name':r[1],'operator':r[4]},
    }

@app.get('/pads/near')
def pads_near(lat: float = Query(...), lon: float = Query(...), radius_km: float = 1000):
    q = '''
    SELECT id, name, lat, lon, operator,
           ST_Distance_Sphere(geom, ST_Point(?, ?))/1000 AS dist_km
    FROM pads
    WHERE ST_Distance_Sphere(geom, ST_Point(?, ?))/1000 < ?
    ORDER BY dist_km
    '''
    rows = con.execute(q, [lon, lat, lon, lat, radius_km]).fetchall()
    return {
        'type':'FeatureCollection',
        'metadata':{'query_lat': lat, 'query_lon': lon, 'radius_km': radius_km, 'match_count': len(rows)},
        'features':[{
            'type':'Feature',
            'geometry':{'type':'Point','coordinates':[r[3], r[2]]},
            'properties':{'id':r[0],'name':r[1],'operator':r[4],'dist_km':round(r[5],2)},
        } for r in rows],
    }

print('FastAPI app defined with 4 endpoints: /health, /pads, /pads/{id}, /pads/near')"""))

cells.append(md("""## Step 3 — Run the server in-process and hit it with httpx"""))
cells.append(code(
"""import asyncio, nest_asyncio, httpx, uvicorn
nest_asyncio.apply()

config = uvicorn.Config(app, host='127.0.0.1', port=8001, log_level='error')
server = uvicorn.Server(config)

async def run():
    task = asyncio.create_task(server.serve())
    # Give uvicorn a moment to bind the port
    await asyncio.sleep(0.6)

    async with httpx.AsyncClient(base_url='http://127.0.0.1:8001') as cli:
        # /health
        r = await cli.get('/health')
        print(f'GET /health  →  {r.status_code}  {r.json()}')

        # /pads?operator=SpaceX
        r = await cli.get('/pads', params={'operator':'SpaceX'})
        d = r.json()
        print(f'GET /pads?operator=SpaceX  →  {len(d[\"features\"])} pads')
        for f in d['features']:
            print(f'    - {f[\"properties\"][\"name\"]}  ({f[\"geometry\"][\"coordinates\"][1]:.2f}, {f[\"geometry\"][\"coordinates\"][0]:.2f})')

        # /pads/near?lat=21.31&lon=-157.86&radius_km=10000  (Honolulu, big radius)
        r = await cli.get('/pads/near', params={'lat': 21.31, 'lon': -157.86, 'radius_km': 10000})
        d = r.json()
        print(f'\\nGET /pads/near  →  {d[\"metadata\"][\"match_count\"]} matches within 10000 km of Honolulu')
        for f in d['features'][:5]:
            print(f'    - {f[\"properties\"][\"name\"]:<22s}  {f[\"properties\"][\"dist_km\"]:>9,.0f} km')

    server.should_exit = True
    await task
    print('\\n[server] shut down cleanly.')

asyncio.run(run())"""))

cells.append(md(
"""## Step 4 — Drop-in production swap to PostGIS

Replace the DuckDB connection with `asyncpg` + a `geography` column, and every query above runs unchanged:

```python
# Local (this notebook)
con = duckdb.connect(':memory:')
con.execute('INSTALL spatial; LOAD spatial;')

# Production
import asyncpg
con = await asyncpg.connect('postgres://user:pw@host:5432/db')
# ST_Point / ST_Distance_Sphere live in the postgis extension — same SQL.
```

FastAPI auto-generates OpenAPI documentation at `/docs` (Swagger UI) and `/redoc`. In production add:

- **CORS** middleware (`fastapi.middleware.cors.CORSMiddleware`) for browser clients.
- **Rate limit** middleware (`slowapi`).
- **Auth**: bearer-token dependency (`from fastapi import Security`).
- **Health checks**: extend `/health` to ping the DB.

## Common gotchas

- **GeoJSON coordinate order is `[lon, lat]`** — easy to flip in JSON construction. The DB returns `(lat, lon)`; the JSON wants `(lon, lat)`. Get the order wrong and your maps render in the wrong hemisphere.
- **`/pads/near` competes with `/pads/{id}` in FastAPI routing.** Order matters — put the more-specific routes (`/pads/near`) BEFORE generic ones (`/pads/{id}`) in your @app.get definitions, otherwise FastAPI tries to parse "near" as an int id.
- **DuckDB connections are not thread-safe.** Use `asyncpg` + a connection pool for production; or use `threading.Lock` around DuckDB calls.
- **OpenAPI schema for spatial data**: GeoJSON isn't in pydantic's default types. Use `pydantic-geojson` or define your own `BaseModel` for the response.
"""))

cells.append(md(
"""## Self-check
- [ ] FastAPI server starts in-process, all four endpoints respond.
- [ ] `/health` returns `{'status': 'ok'}`.
- [ ] `/pads?operator=SpaceX` returns 3 pads (SLC-40, LC-39A, SLC-4E).
- [ ] `/pads/near?lat=21.31&lon=-157.86&radius_km=10000` returns all 8 pads sorted by distance.
- [ ] Server shuts down cleanly without hanging the notebook kernel.
- [ ] Quiz on the [Week 29 page](https://launchdetect.com/academy/week/29/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-29/lab.ipynb ({len(cells)} cells)")
