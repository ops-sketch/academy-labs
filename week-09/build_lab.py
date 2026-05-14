"""Build week-09/lab.ipynb — Ground-to-satellite line-of-sight and coverage.

Upgrade: given a ground station (user-configurable, defaults to Honolulu),
compute the next 24h of ISS passes — rise/culmination/set times, peak
elevation, azimuth — and filter to "good" passes (peak elevation > 30°).
Implements the TODO from the old skeleton.
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
"""# Week 9: Ground-to-satellite line-of-sight and coverage

**Track:** Orbital Analyst (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/9/](https://launchdetect.com/academy/week/9/)

---

_When can your ground station SEE the satellite? That's the core question of pass prediction. This week you compute the next 24 hours of ISS passes over a ground station you choose, filter to "good" ones (≥30° peak elevation), and print a station-schedule-quality table — the same format an ops team would consume._
"""))

cells.append(md(
"""## Why this week matters

Every ground-station operation revolves around passes. Antenna pointing, data downlink windows, telemetry plots, regulatory licensing, even amateur visual observation — all of it needs "when is this satellite over me, and how high?"

Three concepts:

- **Elevation angle** — height above horizon. 0° = on horizon, 90° = directly overhead. Most antennas need at least ~5° for usable signal; visual observation needs ~10°; high-rate downlinks want 30°+.
- **Azimuth angle** — compass bearing from your station to the satellite. 0° = north, 90° = east.
- **Pass** — the contiguous time window where elevation > some threshold. A typical ISS pass at mid-latitudes is 6-10 minutes long.
"""))

cells.append(code(
"""!pip install -q skyfield numpy requests"""))

cells.append(md(
"""## Step 1 — Pick your ground station

Defaults to Honolulu (LaunchDetect HQ — Mauna Kea has actual radio telescopes). Override `STATION` to your own location.
"""))

cells.append(code(
"""# Ground station — change these to your own
STATION_NAME = "Honolulu, Hawaiʻi"
STATION_LAT  =  21.3099
STATION_LON  = -157.8581
STATION_ELEV =  10  # meters above ellipsoid

# Pass-quality threshold
MIN_PEAK_ELEV_DEG = 30  # only count passes that culminate above 30° (good passes)
HORIZON_DEG       = 0   # 'pass' begins when sat crosses 0° elevation

print(f"Station: {STATION_NAME}  ({STATION_LAT:+.4f}, {STATION_LON:+.4f}, {STATION_ELEV} m)")
print(f"Looking for ISS passes with peak elevation > {MIN_PEAK_ELEV_DEG}° in the next 24 h.")"""))

cells.append(md(
"""## Step 2 — Live TLE + skyfield setup
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

from skyfield.api import EarthSatellite, load, wgs84
from datetime import timedelta

name, line1, line2, src = fetch_iss_tle()
print(f"TLE source: {src}")

ts  = load.timescale()
sat = EarthSatellite(line1, line2, name, ts)
station = wgs84.latlon(STATION_LAT, STATION_LON, elevation_m=STATION_ELEV)"""))

cells.append(md(
"""## Step 3 — Find passes with `find_events`

Skyfield's `sat.find_events(observer, t0, t1, altitude_degrees=H)` returns the rise / culmination / set sequence above `H`. We use `altitude_degrees=0` for the horizon-crossing pass envelope, then check each culmination's actual elevation to filter for quality.
"""))

cells.append(code(
"""now = ts.now()
end = ts.from_datetime(now.utc_datetime() + timedelta(hours=24))

times_ev, events = sat.find_events(station, now, end, altitude_degrees=HORIZON_DEG)
# events: 0 = rise, 1 = culminate, 2 = set

passes = []
i = 0
while i < len(events) - 2:
    if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2:
        t_rise, t_culm, t_set = times_ev[i], times_ev[i+1], times_ev[i+2]
        diff = (sat - station).at(t_culm)
        alt, az, _ = diff.altaz()
        peak_elev = alt.degrees
        peak_az   = az.degrees
        passes.append({
            'rise_utc':  t_rise.utc_datetime(),
            'culm_utc':  t_culm.utc_datetime(),
            'set_utc':   t_set.utc_datetime(),
            'peak_elev': peak_elev,
            'peak_az':   peak_az,
            'duration_s': (t_set.utc_datetime() - t_rise.utc_datetime()).total_seconds(),
        })
        i += 3
    else:
        i += 1

print(f"Total horizon-crossing passes in next 24h: {len(passes)}")"""))

cells.append(md(
"""## Step 4 — Filter and print the schedule

Operators care about passes that **actually clear obstructions** — buildings, trees, terrain. The 30°-peak rule is a conservative proxy that captures "good" visibility for most ground stations.
"""))

cells.append(code(
"""def compass(az):
    pts = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
    return pts[int((az + 11.25) // 22.5) % 16]

good = [p for p in passes if p['peak_elev'] >= MIN_PEAK_ELEV_DEG]
print(f"Passes with peak elevation ≥ {MIN_PEAK_ELEV_DEG}°: {len(good)} / {len(passes)}")
print()
print(f"{'Rise (UTC)':<20} {'Peak (UTC)':<20} {'Set (UTC)':<20} {'Dur':>5} {'Peak elev':>10} {'Peak az':>10}")
print('-' * 92)
for p in good:
    rise = p['rise_utc'].strftime('%Y-%m-%d %H:%M:%S')
    culm = p['culm_utc'].strftime('%Y-%m-%d %H:%M:%S')
    sset = p['set_utc'].strftime('%Y-%m-%d %H:%M:%S')
    print(f"{rise:<20} {culm:<20} {sset:<20} {int(p['duration_s']/60):>4}m {p['peak_elev']:>8.1f}° {p['peak_az']:>5.1f}° {compass(p['peak_az'])}")

if good:
    longest = max(good, key=lambda p: p['duration_s'])
    overhead = max(good, key=lambda p: p['peak_elev'])
    print()
    print(f"Longest pass:      {int(longest['duration_s']/60)}m {int(longest['duration_s']%60)}s, peak {longest['peak_elev']:.1f}°")
    print(f"Highest pass:      peak {overhead['peak_elev']:.1f}° (closest to zenith)")
else:
    print("No high-elevation passes in the next 24 h — try a different station or wait for the orbit to precess.")"""))

cells.append(md(
"""## Step 5 — Plot a single pass's elevation curve

The peak-elevation number summarizes a pass; the elevation curve tells you what the antenna actually has to track.
"""))

cells.append(code(
"""import numpy as np
import matplotlib.pyplot as plt

if good:
    target = good[0]
    # 1-second samples across the pass duration
    start = ts.from_datetime(target['rise_utc'])
    finish = ts.from_datetime(target['set_utc'])
    t_arr = ts.linspace(start, finish, max(int(target['duration_s']) + 1, 60))
    diff = (sat - station).at(t_arr)
    alt, az, _ = diff.altaz()
    seconds = np.arange(len(alt.degrees))

    fig, ax = plt.subplots(figsize=(11, 4), dpi=110)
    ax.plot(seconds, alt.degrees, color='#0891b2', linewidth=2.5)
    ax.fill_between(seconds, 0, alt.degrees, alpha=0.15, color='#0891b2')
    ax.axhline(MIN_PEAK_ELEV_DEG, color='#dc2626', linestyle='--', label=f'{MIN_PEAK_ELEV_DEG}° threshold')
    ax.set_xlabel('Seconds since rise')
    ax.set_ylabel('Elevation (°)')
    title = f"First good pass: {target['rise_utc'].strftime('%Y-%m-%d %H:%M:%S UTC')}, peak {target['peak_elev']:.1f}°"
    ax.set_title(title)
    ax.legend(); ax.grid(True, alpha=0.4)
    ax.set_ylim(0, 90)
    plt.tight_layout()
    plt.show()
else:
    print("No good pass to plot. Try lowering MIN_PEAK_ELEV_DEG or extending the search window.")"""))

cells.append(md(
"""## Common gotchas

- **`sat - station` is a vector subtraction.** It returns a topocentric position. `.altaz()` then gives elevation + azimuth + range.
- **Azimuth from `altaz()` is measured FROM NORTH, EASTWARD.** 90° = due east, 180° = south, 270° = west.
- **Refraction.** Skyfield's `altaz(temperature_C=…, pressure_mbar=…)` corrects for atmospheric refraction at low elevations. We're not using it — refraction lifts apparent elevation by ~0.5° at the horizon, dropping to ~0.02° at 30°.
- **The 30° threshold is a heuristic.** Below ~30° elevation, slant range to the satellite is much longer, atmospheric attenuation is worse, and ground obstructions dominate. But high-gain antennas operate at 5°; visual observation works at 10°. Pick threshold per use case.
- **TLE epoch drift.** Use a TLE within 7 days of the prediction window. Older TLEs accumulate cross-track error fast.
"""))

cells.append(md(
"""## Self-check

- [ ] At least one ISS pass found in the next 24h (Honolulu typically gets 3-6 passes/day; high-latitude stations get more).
- [ ] At least one pass with peak elevation ≥ 30° exists somewhere in the next 3 days (try extending the window).
- [ ] Pass schedule prints rise / culmination / set timestamps in UTC.
- [ ] Elevation curve for the first good pass shows a bell-shaped rise → peak → set.
- [ ] Quiz on the [Week 9 page](https://launchdetect.com/academy/week/9/).

## What's next

**Week 10 — Capstone 2.** Combine the live TLE, ground track, coverage polygon, and pass prediction into one notebook that mints the **Orbital Analyst** credential.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-09/lab.ipynb ({len(cells)} cells)")
