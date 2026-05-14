"""Build week-25/lab.ipynb — AR sky-direction overlays: az/el from your location."""
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
"""# Week 25: AR overlays — sky direction (az, elevation) from your location

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/25/](https://launchdetect.com/academy/week/25/)

---

_When the user wants to **point their phone at the sky and see the ISS**, you need (lat, lon, time) → (azimuth, elevation) per satellite, then a projection from horizontal sky-coordinates to screen pixels via the phone's gyroscope. The orbital-mechanics half is Week 9; the screen-projection half is new. This week shows both, with a runnable demo._
"""))

cells.append(md("""## Why this week matters

LaunchDetect's mobile AR feature lets a user point their phone at any horizon and see overlaid markers for visible satellite passes. The pipeline:

1. **Skyfield** computes (azimuth, elevation) for each tracked satellite from the user's GPS coordinates (Week 9).
2. The phone's gyroscope reports the device's orientation (yaw, pitch, roll) in a world-aligned frame.
3. For each satellite: if the angular distance from the phone's pointing axis is within the camera's FOV, draw a marker at the projected screen position.

This week implements steps 1+3 (the math); step 2 is platform-specific (DeviceOrientationEvent / iOS CoreMotion)."""))

cells.append(code("""!pip install -q skyfield numpy matplotlib"""))

cells.append(md("""## Step 1 — Azimuth + elevation for all visible satellites"""))
cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
from datetime import timedelta
import numpy as np
import requests

# Your location
OBS_LAT, OBS_LON = 21.3099, -157.8581  # Honolulu

# A few satellite TLEs (ISS + 3 Starlinks for variety). Live-fetch in production.
TLES = [
    ('ISS','1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
           '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361'),
]
try:
    j = requests.get('https://tle.ivanstanojevic.me/api/tle?search=STARLINK&pageSize=5', timeout=10).json()
    for d in j.get('member', [])[:5]:
        TLES.append((d['name'], d['line1'], d['line2']))
except Exception:
    pass

ts = load.timescale(); now = ts.now()
observer = wgs84.latlon(OBS_LAT, OBS_LON, 0)

visible = []
for (name, l1, l2) in TLES:
    try:
        sat = EarthSatellite(l1, l2, name, ts)
        diff = (sat - observer).at(now)
        alt, az, _ = diff.altaz()
        if alt.degrees > 0:  # above horizon
            visible.append({'name': name.strip(), 'az_deg': float(az.degrees), 'el_deg': float(alt.degrees)})
    except Exception:
        continue
print(f'Above horizon at {now.utc_strftime(\"%H:%M:%S\")}:')
for v in visible:
    print(f'  {v[\"name\"]:<24s}  az {v[\"az_deg\"]:>6.1f}°  el {v[\"el_deg\"]:>5.1f}°')"""))

cells.append(md(
"""## Step 2 — Project (az, el) onto a phone screen

The phone's camera points in a direction defined by (yaw, pitch) where:
- **yaw** = the compass direction the camera back is facing (0° = north, 90° = east)
- **pitch** = the angle above (positive) or below (negative) horizontal

To project a satellite at (az, el) onto the screen: rotate the satellite's horizontal-frame vector into the camera frame, then perspective-project through the focal length.
"""))
cells.append(code(
"""# Camera parameters: 60° horizontal FOV, 60° vertical (typical phone front-camera)
CAM_FOV_HORIZ = 60.0  # degrees
CAM_FOV_VERT  = 90.0  # iPhone portrait is ~90° vertical
SCREEN_W, SCREEN_H = 390, 844  # iPhone 14 pixel dimensions (CSS reference)

def az_el_to_xyz(az_deg, el_deg):
    az = np.deg2rad(az_deg); el = np.deg2rad(el_deg)
    # +x = east, +y = north, +z = up (ENU frame)
    return np.array([np.cos(el)*np.sin(az), np.cos(el)*np.cos(az), np.sin(el)])

def world_to_screen(sat_xyz, camera_yaw_deg, camera_pitch_deg):
    \"\"\"Project an ENU-frame point onto the camera's screen.

    Returns (x, y) in screen pixels with (0,0) at top-left and y-down,
    or None if the satellite is behind the camera.\"\"\"
    yaw = np.deg2rad(camera_yaw_deg)
    pitch = np.deg2rad(camera_pitch_deg)

    # Rotate world → camera frame: first un-yaw (rotate around z), then un-pitch (around x)
    cy, sy = np.cos(-yaw), np.sin(-yaw)
    cp, sp = np.cos(-pitch), np.sin(-pitch)
    # After un-yaw, the camera looks down +y
    Rz = np.array([[cy, -sy, 0],[sy, cy, 0],[0, 0, 1]])
    # After un-pitch, the camera looks down +y still, with horizon at z=0
    Rx = np.array([[1, 0, 0],[0, cp, -sp],[0, sp, cp]])
    cam = Rx @ Rz @ sat_xyz
    if cam[1] <= 0:
        return None  # behind camera

    # Pinhole projection: x_screen ~ cam_x / cam_y, scaled by focal length
    fx = SCREEN_W / (2 * np.tan(np.deg2rad(CAM_FOV_HORIZ/2)))
    fy = SCREEN_H / (2 * np.tan(np.deg2rad(CAM_FOV_VERT/2)))
    x_pix = SCREEN_W/2 + fx * cam[0] / cam[1]
    y_pix = SCREEN_H/2 - fy * cam[2] / cam[1]
    return (x_pix, y_pix)

# Imagine the user pointing their phone yaw=180° (south), pitch=+30° (above horizon).
CAM_YAW = 180.0; CAM_PITCH = 30.0
print(f'Camera: yaw={CAM_YAW}°, pitch={CAM_PITCH}°')
print()
print(f'{\"Satellite\":<24s}  {\"az\":>6s} {\"el\":>5s}  {\"screen (px)\":>18s}')
for v in visible:
    xyz = az_el_to_xyz(v['az_deg'], v['el_deg'])
    px = world_to_screen(xyz, CAM_YAW, CAM_PITCH)
    if px is None:
        screen = 'BEHIND'
    elif 0 <= px[0] <= SCREEN_W and 0 <= px[1] <= SCREEN_H:
        screen = f'({px[0]:.0f}, {px[1]:.0f}) ✓ in view'
    else:
        screen = f'({px[0]:.0f}, {px[1]:.0f}) off-screen'
    print(f'{v[\"name\"]:<24s}  {v[\"az_deg\"]:>6.1f} {v[\"el_deg\"]:>5.1f}  {screen:>18}')"""))

cells.append(md(
"""## Step 3 — Render the sky map (debug visualization)

The phone-screen view above is the AR rendering target. The all-sky polar plot below is the standard debug view: zenith at center, horizon at radius 1, azimuth as angle. This is the view that hardware-store digital sextants and astronomy apps show.
"""))
cells.append(code(
"""import matplotlib.pyplot as plt

fig = plt.figure(figsize=(8,8), dpi=110)
ax = plt.subplot(111, projection='polar')
ax.set_theta_zero_location('N')  # 0° at top (north)
ax.set_theta_direction(-1)        # azimuth increases clockwise
ax.set_rlim(0, 90)                # radius is zenith-angle (90 - elevation)
ax.set_rticks([15, 30, 45, 60, 75])
ax.set_rgrids([15, 30, 45, 60, 75], labels=['75°','60°','45°','30°','15°'])

for v in visible:
    az_rad = np.deg2rad(v['az_deg'])
    zen = 90 - v['el_deg']
    color = '#dc2626' if 'ISS' in v['name'] else '#0891b2'
    ax.scatter(az_rad, zen, s=120, c=color, edgecolor='#222', zorder=3)
    ax.annotate(v['name'][:14], (az_rad, zen), textcoords='offset points', xytext=(8, 4), fontsize=9)

# Camera FOV rectangle on the polar plot
cam_az = np.deg2rad(CAM_YAW); cam_zen = 90 - CAM_PITCH
ax.plot([cam_az, cam_az], [0, 90], color='#15803d', linestyle='--', alpha=0.6, label='Camera yaw')
ax.set_title(f'Sky map — Honolulu {now.utc_strftime(\"%Y-%m-%d %H:%M UTC\")}', pad=20)
ax.legend(loc='upper right')
plt.tight_layout(); plt.show()"""))

cells.append(md("""## Step 4 — On the phone: DeviceOrientationEvent

The browser/iOS gives you yaw/pitch via `DeviceOrientationEvent` (web) or `CMMotionManager` (iOS native). The minimal JS for the web variant:

```javascript
window.addEventListener('deviceorientation', (e) => {
  const yaw   = e.webkitCompassHeading ?? e.alpha;  // 0=N, 90=E
  const pitch = e.beta;                              // tilt fwd/back
  const roll  = e.gamma;                             // tilt left/right
  redrawAROverlays(yaw, pitch);
});
```

Pass `(yaw, pitch)` into the `world_to_screen` function from Step 2 and render markers. The math is identical."""))

cells.append(md(
"""## Common gotchas

- **Compass calibration drift.** Phone magnetometers wobble by ±10°; users see satellites shift on screen. Apply a Kalman filter or rely on visual SLAM.
- **Refraction at low elevation.** Below ~5° elevation, atmospheric refraction lifts apparent position by ~0.5°. Negligible for AR; matters for ground-station antenna pointing.
- **iOS permission for `DeviceOrientationEvent`** requires an explicit user gesture + `permission` request. Skipped permissions silently return no data.
- **Web Mercator's z=0 horizon != real horizon.** When fusing AR overlay with a map view, the horizon line is at view-plane z=0 in the AR camera, not at any specific map tile.
- **GPS lat/lon precision matters.** ±10 m at the user's location pushes the ISS computed position by 10 m × tan(elevation) — typically sub-arcsecond, negligible. But matters at the equator from a moving vehicle.
"""))

cells.append(md(
"""## Self-check
- [ ] Az/El computed for ≥ 1 visible satellite (ISS + maybe Starlinks).
- [ ] Projecting a satellite at the camera's exact pointing direction lands it near screen center.
- [ ] Satellites behind the camera (cam_y < 0) return `None` from `world_to_screen`.
- [ ] Sky-map polar plot renders with satellites at correct positions; ISS in red, Starlinks in blue.
- [ ] You can articulate the gyroscope → camera-frame rotation chain in three lines of math.
- [ ] Quiz on the [Week 25 page](https://launchdetect.com/academy/week/25/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-25/lab.ipynb ({len(cells)} cells)")
