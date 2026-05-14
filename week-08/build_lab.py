"""Build week-08/lab.ipynb — SGP4 propagation with skyfield.

Upgrade: live TLE fetch, propagate to NOW and to NOW+7 days, compute
sub-satellite track + altitude + velocity, verify against known physics
(ISS altitude 400-420 km, orbital velocity ~7.66 km/s, period ~92.95 min).
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
"""# Week 8: SGP4 propagation in Python with skyfield

**Track:** Orbital Analyst (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/8/](https://launchdetect.com/academy/week/8/)

---

_Week 7 you learned to **read** a TLE. This week you **propagate** it — turn (TLE + future time) into (lat, lon, altitude, velocity) at that future time. The math is SGP4, decades of edge cases. The library is skyfield. The discipline is knowing when to trust the answer._
"""))

cells.append(md(
"""## Why this week matters

Every "where will the satellite be at time T?" question routes through SGP4. It's the standard model for near-Earth orbits (LEO up to GEO) and embedded in every commercial tracker, every ground-station scheduler, every LaunchDetect-style geostationary alignment tool. Accuracy decays at roughly **1-3 km/day** after the TLE epoch — fresh TLE = sub-km accuracy; week-old TLE = several km off; month-old TLE = useful only for "general where".
"""))

cells.append(md(
"""## Learning objectives

- Propagate a TLE forward in time with `skyfield`
- Compute sub-satellite latitude/longitude
- Compute altitude above the ellipsoid and instantaneous velocity
- Identify SGP4's accuracy decay vs TLE age
- Distinguish geocentric (sat.at(t).position) from geodetic (wgs84.subpoint_of)
"""))

cells.append(code(
"""!pip install -q skyfield numpy requests"""))

cells.append(md(
"""## Step 1 — Live TLE (same as Week 7)
"""))

cells.append(code(
"""import requests
def fetch_iss_tle():
    try:
        r = requests.get("https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE", timeout=8)
        if r.ok and r.text.strip().startswith("ISS"):
            ls = r.text.strip().splitlines()
            return ls[0].strip(), ls[1].strip(), ls[2].strip(), "celestrak"
    except: pass
    try:
        j = requests.get("https://tle.ivanstanojevic.me/api/tle/25544", timeout=8).json()
        return j["name"], j["line1"], j["line2"], "ivanstanojevic mirror"
    except: pass
    return ("ISS (ZARYA)",
            "1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993",
            "2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361",
            "embedded fallback")

name, line1, line2, src = fetch_iss_tle()
print(f"Source: {src}")
print(f"  {line1}")
print(f"  {line2}")"""))

cells.append(md(
"""## Step 2 — Propagate to NOW

The pattern is always: build `EarthSatellite` → choose a `Time` → call `sat.at(t)` → extract what you want. `wgs84.subpoint_of` collapses the 3D position to its lat/lon shadow on the WGS84 ellipsoid.
"""))

cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
import numpy as np

ts = load.timescale()
sat = EarthSatellite(line1, line2, name, ts)
now = ts.now()

geocentric = sat.at(now)
sub = wgs84.subpoint_of(geocentric)

lat_now = sub.latitude.degrees
lon_now = sub.longitude.degrees
alt_now_km = wgs84.height_of(geocentric).km

# Velocity: derivative of position vector. .velocity.km_per_s gives [vx, vy, vz] in km/s.
v_kms = float(np.linalg.norm(geocentric.velocity.km_per_s))

print(f"ISS RIGHT NOW (per the latest TLE):")
print(f"  lat:        {lat_now:+8.4f}°")
print(f"  lon:        {lon_now:+8.4f}°")
print(f"  altitude:   {alt_now_km:7.2f} km")
print(f"  velocity:   {v_kms:6.3f} km/s   ({v_kms*3600:.0f} km/h)")
print()
# Sanity checks: ISS lives in a tight envelope.
assert 380 < alt_now_km < 440,   f"altitude {alt_now_km} outside ISS envelope"
assert  7.5 < v_kms      < 7.85, f"velocity {v_kms} outside ISS envelope"
assert -52  < lat_now    < 52,   f"lat {lat_now} outside ISS inclination band"
print("[PASS] altitude/velocity/lat are inside the ISS's known physical envelope.")"""))

cells.append(md(
"""## Step 3 — Propagate over a full orbit, plot altitude vs time

The ISS orbit is near-circular (e ≈ 0.0007522), so the perigee-apogee altitude difference from eccentricity alone is `a × 2e ≈ 10 km`. But the plot you're about to see shows the altitude breathing more like **25-30 km**. That's not a bug — that's **Earth's oblateness** showing through. The WGS84 ellipsoid is ~21 km wider at the equator than at the poles, and the ISS at 51.6° inclination is sampling both extremes once per orbit. The orbital ellipse contributes the small (~10 km) breathing; the ellipsoid contributes the larger (~15-20 km) part.

This is the kind of detail SGP4-plus-WGS84 captures and a textbook circular orbit hides.
"""))

cells.append(code(
"""from datetime import timedelta

minutes = np.arange(0, 93, 0.5)  # one full orbit, 30-s steps
times = ts.linspace(now, ts.from_datetime(now.utc_datetime() + timedelta(minutes=93)), len(minutes))
geos = sat.at(times)
alt_km = wgs84.height_of(geos).km

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(11, 4), dpi=110)
ax.plot(minutes, alt_km, color='#dc2626', linewidth=2)
ax.fill_between(minutes, alt_km, alpha=0.15, color='#dc2626')
ax.axhline(alt_km.mean(), color='#888', linestyle=':', label=f'mean = {alt_km.mean():.1f} km')
ax.set_xlabel('Minutes from now')
ax.set_ylabel('Altitude above WGS84 ellipsoid (km)')
ax.set_title(f'ISS altitude over one orbit (Δ = {alt_km.max()-alt_km.min():.1f} km, period ≈ 93 min)')
ax.grid(True, alpha=0.4)
ax.legend()
plt.tight_layout()
plt.show()

print(f"Altitude range over one orbit: {alt_km.min():.2f} km → {alt_km.max():.2f} km")
print(f"Total Δh (over WGS84 ellipsoid):     {alt_km.max() - alt_km.min():.2f} km")
print(f"Contributions:")
print(f"  · orbital eccentricity   a·2e ≈ {6797 * 2 * 0.0007522:.2f} km (from Week 7 elements)")
print(f"  · Earth oblateness       up to ~{6378.137 - 6356.752:.1f} km (eq vs pole semi-axes)")
print(f"The measured Δh is the SUM of both. SGP4 + WGS84 captures it; a textbook circular-orbit model would hide it.")"""))

cells.append(md(
"""## Step 4 — Propagate forward 7 days, watch the ground track precess

The orbital plane is inertial (fixed in space). Earth rotates underneath it. Each successive orbit shifts ~22.5° west — that's what makes the famous ground-track sinusoid.
"""))

cells.append(code(
"""# Sample one point per orbit for 7 days
days = 7
samples_per_day = int(24 * 60 / 92.95)  # ~15 per day
n = days * samples_per_day

times7 = ts.linspace(now, ts.from_datetime(now.utc_datetime() + timedelta(days=days)), n)
subs7 = wgs84.subpoint_of(sat.at(times7))
lats7 = subs7.latitude.degrees
lons7 = subs7.longitude.degrees

fig, ax = plt.subplots(figsize=(12, 5), dpi=110)
ax.scatter(lons7, lats7, c=np.arange(n), cmap='plasma', s=8, alpha=0.7)
ax.set_xlabel('Longitude (°E)')
ax.set_ylabel('Latitude (°N)')
ax.set_title(f'ISS sub-satellite samples over next {days} days — colour = time progression')
ax.set_xlim(-180, 180); ax.set_ylim(-60, 60)
ax.grid(True, alpha=0.3)
ax.axhline(0, color='#888', linewidth=0.5)
plt.tight_layout()
plt.show()

print(f"Coverage band over {days} days:")
print(f"  latitude range: {lats7.min():+.2f}° to {lats7.max():+.2f}°")
print(f"  expected:       ±51.63° (inclination)")
assert abs(lats7.max() - 51.6) < 1.0, 'should hit max lat ≈ inclination'
assert abs(lats7.min() + 51.6) < 1.0, 'should hit min lat ≈ -inclination'
print("[PASS] sub-satellite track stays inside ±inclination, as expected.")"""))

cells.append(md(
"""## Common gotchas

- **`subpoint_of` returns a `wgs84.subpoint` object, not a tuple.** Use `.latitude.degrees`, `.longitude.degrees`, `.elevation.m`.
- **`sat.at(t).altitude` does NOT exist.** Use `wgs84.height_of(geocentric)` — there is a real geodetic difference between geocentric distance and geodetic altitude.
- **TLE epoch matters.** A TLE more than ~1 week stale should be refreshed for any pass-prediction work; for "where in the sky" a month is fine.
- **No SGP4 for deep space.** Use SDP4 (which skyfield handles transparently behind the scenes) or higher-fidelity propagators (GMAT, STK, OREKIT) for HEO and beyond.
- **Time is the bug surface.** UTC vs TAI vs GPS time vs leap-seconds. Use `ts.utc(year, month, day, hour, minute, second)` and trust the library.
"""))

cells.append(md(
"""## Self-check

- [ ] Sub-satellite point printed with lat, lon, altitude, velocity.
- [ ] All three sanity assertions PASS (altitude 380-440 km, velocity 7.5-7.85 km/s, |lat| ≤ 52°).
- [ ] Altitude-over-one-orbit plot shows the ~10 km perigee-apogee breathing.
- [ ] 7-day track plot shows the ground sweeping westward with the ±51.6° inclination band visible.
- [ ] Quiz on the [Week 8 page](https://launchdetect.com/academy/week/8/).

## What's next

**Week 9 — Line-of-sight and coverage.** Given your ground station and an orbit, when are the upcoming passes? Which ones rise above 30° elevation? That's how every ground-station scheduler works.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-08/lab.ipynb ({len(cells)} cells)")
