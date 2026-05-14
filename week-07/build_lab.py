"""Build week-07/lab.ipynb — Orbital mechanics primer: TLEs and Keplerian elements.

Upgrade: fetch a live ISS TLE (with multi-mirror fallback), parse it field
by field, and verify the parsed elements match the Keplerian inferences
(inclination, eccentricity, period). Implements the old TODO.
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
"""# Week 7: Orbital mechanics primer — TLEs and Keplerian elements

**Track:** Orbital Analyst (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/7/](https://launchdetect.com/academy/week/7/)

---

_Six numbers tell you everything you need to know about an orbit — those are the **Keplerian elements**. The Two-Line Element set (TLE) packs them into 138 ASCII characters per satellite plus drag and epoch metadata. This week you fetch a **live** ISS TLE, parse it field by field, and verify the orbit it describes._
"""))

cells.append(md(
"""## Why this week matters

Every space-domain analysis you'll ever do starts with "where is the satellite". The answer comes from a TLE — a fixed-width text format that's been the public-tracking standard since 1969. Read it once and you know:

- The orbital plane (inclination + RAAN)
- The shape (eccentricity)
- The orientation in-plane (argument of perigee)
- Where the spacecraft is on the orbit at a known time (mean anomaly + epoch)
- How fast it goes around (mean motion → period)
- Drag effects (B*, n-dot, n-dot-dot)

Everything in Weeks 8, 9, 10, 18, 19, 21 depends on you being fluent here.
"""))

cells.append(md(
"""## Learning objectives

- Read the structure of a TLE line by line: catalog number, epoch, mean motion, inclination, eccentricity
- Convert a TLE epoch to a UTC `datetime`
- Derive orbital period from mean motion (revolutions per day → minutes per rev)
- Identify which fields drive which physical property of the orbit
- Reach for `skyfield.api.EarthSatellite` to do this correctly
"""))

cells.append(code(
"""!pip install -q skyfield requests"""))

cells.append(md(
"""## Step 1 — Fetch a LIVE ISS TLE (with mirror fallback)

CelesTrak is the canonical public source. If it's blocked, `tle.ivanstanojevic.me` mirrors the same data. If both fail, we fall back to an embedded snapshot so the lab still runs.
"""))

cells.append(code(
"""import requests

def fetch_iss_tle():
    try:
        r = requests.get("https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE", timeout=8)
        if r.ok and r.text.strip().startswith("ISS"):
            lines = r.text.strip().splitlines()
            return lines[0].strip(), lines[1].strip(), lines[2].strip(), "celestrak.org"
    except Exception:
        pass
    try:
        j = requests.get("https://tle.ivanstanojevic.me/api/tle/25544", timeout=8).json()
        return j["name"], j["line1"], j["line2"], "tle.ivanstanojevic.me"
    except Exception:
        pass
    return ("ISS (ZARYA)",
            "1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993",
            "2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361",
            "embedded-snapshot (may be stale)")

name, line1, line2, src = fetch_iss_tle()
print(f"Source: {src}\\n")
print(name)
print(line1)
print(line2)"""))

cells.append(md(
"""## Step 2 — Parse the TLE by hand (so you know what's in it)

A TLE is fixed-width. Every column has a meaning. Parsing it by character is the only way to be sure you know what the fields are.

**Line 1:**
```
1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993
```
- col 03-07 `25544` — NORAD catalog number
- col 10-17 `98067A` — international designator (launch year 1998, launch #67, piece A)
- col 19-32 `26133.42450843` — epoch (year-of-century 26, day-of-year 133.42…)
- col 34-43 `.00004829` — first derivative of mean motion (drag)
- col 54-61 `95080-4` — B* drag term (95080 × 10^-4)

**Line 2:**
```
2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361
```
- col 09-16 `51.6310` — **inclination** (deg)
- col 18-25 `112.1825` — **RAAN** (right ascension of ascending node, deg)
- col 27-33 `0007522` — **eccentricity** (decimal, no leading dot: 0.0007522)
- col 35-42 `54.1994` — **argument of perigee** (deg)
- col 44-51 `305.9693` — **mean anomaly** (deg)
- col 53-63 `15.49203550` — **mean motion** (rev/day)
- col 64-68 `56636` — revolution number at epoch
"""))

cells.append(code(
"""import math
from datetime import datetime, timedelta, timezone

# Parse line 1
catnr  = int(line1[2:7])
intl   = line1[9:17].strip()
epoch_yr = int(line1[18:20])  # 2-digit year
epoch_doy = float(line1[20:32])  # day-of-year fractional
epoch_yr_full = 2000 + epoch_yr if epoch_yr < 57 else 1900 + epoch_yr
epoch_dt = datetime(epoch_yr_full, 1, 1, tzinfo=timezone.utc) + timedelta(days=epoch_doy - 1)
ndot   = float(line1[33:43])  # mean-motion 1st deriv

# Parse line 2
incl   = float(line2[8:16])    # deg
raan   = float(line2[17:25])   # deg
ecc    = float("0." + line2[26:33])  # implicit leading dot
argp   = float(line2[34:42])   # deg
ma     = float(line2[43:51])   # deg
mm     = float(line2[52:63])   # rev/day
revnum = int(line2[63:68])

print(f"NORAD ID:              {catnr}")
print(f"Intl designator:       {intl}")
print(f"Epoch (UTC):           {epoch_dt.isoformat()}")
print(f"Inclination:           {incl:.4f}°")
print(f"RAAN:                  {raan:.4f}°")
print(f"Eccentricity:          {ecc:.7f}   ({'near-circular' if ecc < 0.01 else 'eccentric'})")
print(f"Argument of perigee:   {argp:.4f}°")
print(f"Mean anomaly:          {ma:.4f}°")
print(f"Mean motion:           {mm:.6f} rev/day")
print(f"Rev # at epoch:        {revnum}")
print(f"n-dot (drag):          {ndot:+.4e} (rev/day²/2)")"""))

cells.append(md(
"""## Step 3 — Derive the orbit's physical properties

From the six Keplerian elements + epoch you can compute everything. Two of the most useful:

- **Period** = 24 × 60 / mean_motion  (minutes per revolution)
- **Semi-major axis** from Kepler's third law: `a³ = μ / (2π·n)²`, with μ_Earth = 398600.4418 km³/s².
- **Apogee / perigee altitude**: a·(1±e) − R_Earth.
"""))

cells.append(code(
"""MU_EARTH = 398600.4418   # km^3 / s^2
R_EARTH  = 6378.137       # km, WGS84 equatorial

period_min = 24 * 60 / mm
n_rad_per_s = mm * 2 * math.pi / 86400  # mean motion in rad/s
a_km = (MU_EARTH / n_rad_per_s**2) ** (1.0/3.0)
apogee_km  = a_km * (1 + ecc) - R_EARTH
perigee_km = a_km * (1 - ecc) - R_EARTH

print(f"Period:                {period_min:.2f} min")
print(f"Semi-major axis:       {a_km:.2f} km (Earth radius {R_EARTH:.2f})")
print(f"Apogee altitude:       {apogee_km:.1f} km")
print(f"Perigee altitude:      {perigee_km:.1f} km")

# Verify against skyfield's parsed elements — they should agree to 4+ figures.
from skyfield.api import EarthSatellite, load
ts = load.timescale()
sat = EarthSatellite(line1, line2, name, ts)
print()
print(f"Sanity check vs skyfield (.model.no_kozai is rad/min):")
sk_mm_rev_day = sat.model.no_kozai * 1440 / (2 * math.pi)
print(f"  mean motion (skyfield):   {sk_mm_rev_day:.6f} rev/day  | our parse: {mm:.6f}")
print(f"  inclination (skyfield):   {math.degrees(sat.model.inclo):.4f}°    | our parse: {incl:.4f}°")
print(f"  eccentricity (skyfield):  {sat.model.ecco:.7f}            | our parse: {ecc:.7f}")
assert abs(sk_mm_rev_day - mm) < 0.001, 'mean-motion parse mismatch'
assert abs(math.degrees(sat.model.inclo) - incl) < 0.001, 'inclination parse mismatch'
print()
print("[PASS] Hand-parsed TLE matches skyfield's parser — you now know what's in those 138 chars.")"""))

cells.append(md(
"""## Common gotchas

- **2-digit epoch year.** A `26` in the epoch field means 2026; a `99` means 1999. Pivot at 57 (SGP4 convention).
- **Eccentricity has an implicit leading dot.** `0007522` is `0.0007522`, not `0.0007522e-7`.
- **B* drag and n-dot, n-dot-dot are scientific-notation-ish.** `95080-4` is `9.5080e-4`; the sign is in the 6th char.
- **TLEs go stale.** Useful accuracy decays at ~1 km/day. For ranging applications fetch a fresh TLE; for "where roughly" any TLE less than a week old is fine.
- **Don't propagate by hand.** SGP4 is decades of edge cases (sun-sync, deep-space corrections, atmospheric coupling). Use skyfield — that's Week 8.
"""))

cells.append(md(
"""## Self-check

- [ ] Epoch year is 2026 (or whenever the live TLE was fetched).
- [ ] Inclination is ~51.6° (the ISS's orbital plane — set by the Baikonur launch azimuth).
- [ ] Eccentricity is < 0.001 (ISS orbit is near-circular by design).
- [ ] Period is ~92 minutes (15.5 rev/day).
- [ ] Apogee and perigee altitudes are within ~10 km of each other.
- [ ] Sanity check vs skyfield passes (both `assert`s).
- [ ] Quiz on the [Week 7 page](https://launchdetect.com/academy/week/7/).

## What's next

**Week 8 — SGP4 propagation with skyfield.** Take this TLE and predict where the ISS will be in 90 minutes, 12 hours, 7 days. The math is in skyfield; the interpretation is yours.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-07/lab.ipynb ({len(cells)} cells)")
