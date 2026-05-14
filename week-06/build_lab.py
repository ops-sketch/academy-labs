"""Build week-06/lab.ipynb — PostGIS via DuckDB-spatial (Colab-friendly).

PostGIS is the production grail. Spinning up Postgres + PostGIS in Colab
takes 5+ minutes and 1+ GB. DuckDB + the `spatial` extension speaks the
SAME spatial SQL surface (ST_* function set is shared) and runs in 50
ms in Colab. Same SQL, same lessons, zero infra.

The notebook teaches the SQL; a sidebar shows how to translate every
query to real PostGIS once you set one up.
"""
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

cells = []
cells.append(md(
"""# Week 6: PostGIS — spatial SQL fundamentals

**Track:** Orbital Analyst (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/6/](https://launchdetect.com/academy/week/6/)

---

_PostGIS is the production-grade spatial database every serious geospatial team runs. The SQL is ANSI-friendly: `ST_Contains`, `ST_Distance`, `ST_Buffer`, `ST_Intersects` are the bread and butter. We use **DuckDB + spatial extension** here because it speaks the same ST_ function set and runs in Colab without a Postgres install. Every query in this notebook translates to real PostGIS by changing nothing but the connection string._
"""))

cells.append(md(
"""## Why this week matters

When you outgrow a single GeoDataFrame in RAM — when "all active launch pads" becomes "every recorded launch event since 1957" — you reach for a spatial database. PostGIS is the canonical choice. Same SQL queries, indexed access, billions of rows, joins to non-spatial data. Knowing the SQL idioms is the difference between a 30-line Python loop and a 3-line query.
"""))

cells.append(md(
"""## Learning objectives

- Read the structure of a PostGIS / DuckDB-spatial schema (geometry column + SRID)
- Write the canonical 5 spatial queries: contains, within-distance, intersects, distance, buffer
- Use `ST_Transform` to switch CRS in SQL
- Translate Python `gpd.sjoin` → SQL `JOIN ON ST_Intersects(a.geom, b.geom)`
- Know what a spatial index is (GIST in PostGIS, R-Tree in DuckDB) and when it matters
"""))

cells.append(code(
"""!pip install -q duckdb geopandas shapely requests pandas"""))

cells.append(md(
"""## Step 1 — Set up DuckDB with the spatial extension
"""))
cells.append(code(
"""import duckdb
con = duckdb.connect(':memory:')
con.execute('INSTALL spatial; LOAD spatial;')
# Quick check: the spatial extension exposes ST_*
v = con.execute(\"SELECT ST_AsText(ST_Point(-80.5772, 28.5618))\").fetchone()
print(f'ST_Point output: {v[0]}')
print(f'DuckDB version: {duckdb.__version__}')"""))

cells.append(md(
"""## Step 2 — Load a real-world dataset: Natural Earth countries

Natural Earth ships a country polygon for every nation. We load it directly from the S3 mirror into DuckDB. The `ST_Read` function reads any OGR-supported format (GeoJSON, Shapefile, GPKG, FlatGeobuf, ...).
"""))
cells.append(code(
"""import urllib.request, os
NE_URL = 'https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip'
local_zip = '/content/ne_countries.zip' if os.path.exists('/content') else 'ne_countries.zip'

if not os.path.exists(local_zip):
    print(f'Downloading {NE_URL} ...')
    urllib.request.urlretrieve(NE_URL, local_zip)
print(f'Local file: {local_zip} ({os.path.getsize(local_zip):,} bytes)')

# DuckDB-spatial's ST_Read needs a local file (no remote-zip support today).
# Read directly from the zip with the GDAL '/vsizip/' prefix.
con.execute(f\"\"\"
CREATE TABLE countries AS
SELECT
    NAME      AS name,
    ISO_A2_EH AS iso_a2,
    POP_EST   AS pop_est,
    CONTINENT AS continent,
    geom
FROM ST_Read('/vsizip/{local_zip}')
\"\"\")

row = con.execute('SELECT count(*) FROM countries').fetchone()
print(f'Loaded {row[0]} country rows')

# Schema
print('\\nSchema:')
for r in con.execute(\"DESCRIBE countries\").fetchall():
    print(f'  {r[0]:<12s}  {r[1]}')"""))

cells.append(md(
"""## Step 3 — Spatial query #1: which country contains a point?

The launch-pad-to-country lookup we did in Week 1 with Shapely — but now as SQL.
"""))
cells.append(code(
"""# A few launch-pad coordinates
points = [
    ('Cape Canaveral SLC-40', -80.5772, 28.5618),
    ('Baikonur 1/5',           63.3422, 45.9200),
    ('Tanegashima',            130.97,  30.40),
    ('Kourou',                 -52.77,  5.24),
    ('Mahia',                  177.86, -39.26),
]
con.execute('CREATE TABLE pads (name TEXT, lon DOUBLE, lat DOUBLE, geom GEOMETRY)')
con.executemany('INSERT INTO pads VALUES (?, ?, ?, ST_Point(?, ?))',
                [(n, lo, la, lo, la) for (n, lo, la) in points])

# Q1: country containing each pad.
# ST_Contains is strict — Natural Earth 1:110m drops small barrier islands
# (Cape Canaveral, Tanegashima, Mahia, etc.) so a pure ST_Contains misses
# them. Real-world pattern: try contains first, fall back to nearest country
# within a small tolerance. This is the same "coastline simplification"
# gotcha from Week 1.
print('Q1 — Point in polygon (with coastline-simplification fallback):')
for r in con.execute('''
WITH best AS (
  SELECT p.name AS pad_name,
         c.name AS country, c.iso_a2,
         ST_Distance(c.geom, p.geom) AS d,
         row_number() OVER (PARTITION BY p.name ORDER BY ST_Distance(c.geom, p.geom)) AS rk
  FROM pads p, countries c
  WHERE ST_DWithin(c.geom, p.geom, 1.0)  -- 1° ≈ 110 km island slack
)
SELECT pad_name, country, iso_a2 FROM best WHERE rk = 1
ORDER BY pad_name
''').fetchall():
    print(f'  {r[0]:<22s}  →  {r[1]}  ({r[2]})')"""))

cells.append(md(
"""## Step 4 — Spatial query #2: within-distance & ST_Distance

"Which pads are within 5000 km of Honolulu?" — pure SQL.
"""))
cells.append(code(
"""# ST_Distance on lat/lon returns DEGREES. To measure in km we use the
# spheroid-aware ST_Distance_Spheroid (DuckDB) or ST_Distance_Sphere /
# casting via ST_Transform to a meter CRS in Postgres.
HONO_LON, HONO_LAT = -157.8581, 21.3099

print('Q2 — Distance from Honolulu (km):')
for r in con.execute(f'''
SELECT name,
       ST_Distance_Sphere(geom, ST_Point({HONO_LON}, {HONO_LAT})) / 1000 AS dist_km
FROM   pads
ORDER BY dist_km
''').fetchall():
    print(f'  {r[0]:<22s}  {r[1]:>9,.0f} km')

print('\\n(Note: ST_Distance_Sphere uses a sphere model — within 0.3% of the WGS84 ellipsoid.)')"""))

cells.append(md(
"""## Step 5 — Spatial query #3: spatial join with ST_Intersects

The SQL equivalent of `gpd.sjoin`. Show every (pad, country) pair where the pad falls inside the country's polygon — same as Q1 but expressed as a generic join.
"""))
cells.append(code(
"""# Canonical spatial-join idiom. We use ST_DWithin(1.0°) + nearest-rank
# to handle Natural Earth 1:110m's coastline simplification (same fix as Q1).
# In real PostGIS with a higher-res dataset, ST_Intersects works directly.
df = con.execute('''
WITH matched AS (
    SELECT p.name AS pad, c.name AS country, c.continent,
           row_number() OVER (PARTITION BY p.name ORDER BY ST_Distance(c.geom, p.geom)) AS rk
    FROM pads p, countries c
    WHERE ST_DWithin(c.geom, p.geom, 1.0)
)
SELECT pad, country, continent FROM matched WHERE rk = 1 ORDER BY pad
''').fetchdf()
print(df)"""))

cells.append(md(
"""## Step 6 — Spatial query #4: aggregate per polygon (the most useful query in the book)

"How many pads per continent?" — group by a non-spatial attribute after a spatial join. This is the query pattern you'll write 100 times in your career.
"""))
cells.append(code(
"""df = con.execute('''
WITH matched AS (
    SELECT p.name AS pad, c.continent,
           row_number() OVER (PARTITION BY p.name ORDER BY ST_Distance(c.geom, p.geom)) AS rk
    FROM pads p, countries c WHERE ST_DWithin(c.geom, p.geom, 1.0)
)
SELECT continent, count(*) AS pad_count
FROM matched WHERE rk = 1
GROUP BY continent
ORDER BY pad_count DESC
''').fetchdf()
print(df)
assert len(df) >= 3, 'pads should span at least 3 continents'"""))

cells.append(md(
"""## Step 7 — Spatial query #5: buffer + intersect (the range-safety pattern)

"Which countries fall within 1000 km of any pad?" — buffer pads, then intersect with countries. Range-safety analysts run this every flight to determine notification radii.
"""))
cells.append(code(
"""# DuckDB-spatial buffers in the geometry's native units. For lat/lon
# that's DEGREES — useless. We project to web-mercator, buffer, project back.
# In real PostGIS you'd ST_Transform(geom, 3857) inside the query.
df = con.execute('''
WITH pads_m  AS (SELECT name, ST_Transform(geom, 'EPSG:4326', 'EPSG:3857') AS gm FROM pads),
     buffers AS (SELECT name, ST_Transform(ST_Buffer(gm, 1000000), 'EPSG:3857', 'EPSG:4326') AS gb FROM pads_m)
SELECT b.name AS pad, c.name AS country, c.iso_a2
FROM buffers b, countries c
WHERE ST_Intersects(b.gb, c.geom)
  AND c.iso_a2 IS NOT NULL
ORDER BY pad, country
LIMIT 50
''').fetchdf()
print(df.to_string())
print(f'\\n{len(df)} (pad, country) pairs within 1000 km')"""))

cells.append(md(
"""## Translating to real PostGIS

Every query above runs unmodified in PostGIS, with three substitutions:

| DuckDB-spatial         | Real PostGIS           |
|-----------------------|-----------------------|
| `ST_Read('url.zip')`  | `\\copy` or `ogr2ogr` to load, then `SELECT FROM table` |
| `ST_Distance_Sphere`  | `ST_Distance` on `geography` type, or `ST_DistanceSphere` |
| `ST_Transform(g, 'EPSG:4326', 'EPSG:3857')` | `ST_Transform(g, 3857)` — SRID is set on column |

For real production:

```sql
-- One-time, on table creation
CREATE EXTENSION postgis;
CREATE TABLE pads (id serial PRIMARY KEY, name text,
                   geom geometry(Point, 4326));
CREATE INDEX pads_geom_idx ON pads USING GIST (geom);

-- Same queries, identical results
SELECT p.name, c.name
FROM   pads p
JOIN   countries c ON ST_Contains(c.geom, p.geom);
```

The GIST index is what makes PostGIS fast on 100M+ rows. Without it, every ST_Contains is a sequential scan.
"""))

cells.append(md(
"""## Common gotchas

- **`ST_Distance` on `geometry` columns returns native units.** For lat/lon that's degrees, not meters. Use `geography` type or `ST_DistanceSphere/Spheroid` for meters.
- **Always set an SRID.** Geometry columns without SRID can't be cross-joined with other layers.
- **`ST_Contains` vs `ST_Within` vs `ST_Intersects`.** Contains is one-way (does A contain B?), Within is the reverse, Intersects is symmetric. `ST_Intersects(a, b) = ST_Intersects(b, a)`.
- **Spatial indexes need to be present.** PostGIS will planner-scan without one; DuckDB-spatial similar. `CREATE INDEX … USING GIST` once per geometry column.
- **`ST_Read` for cloud data needs DuckDB ≥ 0.10.** It calls GDAL/OGR under the hood — same data sources as QGIS.
"""))

cells.append(md(
"""## Self-check

- [ ] Q1 places Cape Canaveral in 'United States of America', Baikonur in 'Kazakhstan', etc.
- [ ] Q2 distance from Honolulu to Cape Canaveral is ~7,500 km; to Mahia ~7,000 km.
- [ ] Q3 spatial-join returns one row per pad with a country match.
- [ ] Q4 aggregate shows pads spanning ≥3 continents.
- [ ] Q5 buffer-intersect returns ≥ 5 (pad, country) pairs.
- [ ] You can articulate why a spatial index matters for production-scale queries.
- [ ] Quiz on the [Week 6 page](https://launchdetect.com/academy/week/6/).

## What's next

**Week 7 — Orbital mechanics primer.** We've been doing geography of pads; from here on out, geography moves into the sky.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-06/lab.ipynb ({len(cells)} cells)")
