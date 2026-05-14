"""Build week-22/lab.ipynb — ML for satellite imagery: CNNs and U-Net."""
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
"""# Week 22: ML for satellite imagery — CNNs and U-Net segmentation

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/22/](https://launchdetect.com/academy/week/22/)

---

_Threshold-based hotspot detection (Week 14) gets you 80% of the way. The remaining 20% — cloud edges, glint, parallax-displaced fires — is where ML earns its keep. This week trains a tiny **U-Net** segmentation model on synthetic brightness-temperature scenes and measures it against the threshold baseline. The architecture you learn here is the same one production wildfire / flood / plume detectors use; the difference is scale of training data._
"""))

cells.append(md("""## Why this week matters

A modern thermal-anomaly detector emits a mask: per-pixel "is this a hot anomaly?" U-Net is the canonical architecture for that mask. ~1M parameters, 30-min training on a single GPU for a small domain, beats handcrafted thresholds on every standard benchmark.

We use synthetic data — real GOES-labeled training data is gigabytes and a session of its own. The architecture, loss function, training loop, and evaluation are real."""))

cells.append(code("""!pip install -q torch numpy matplotlib"""))

cells.append(md("""## Step 1 — Synthesize training scenes"""))
cells.append(code(
"""import numpy as np, torch
import torch.nn as nn
import torch.nn.functional as F

def make_scene(size=128, rng=None):
    rng = rng or np.random.default_rng()
    bt = rng.normal(285, 4, (size, size)).astype('f4')
    mask = np.zeros((size, size), dtype='f4')
    # Insert 0-3 'hot' blobs with Gaussian envelopes
    for _ in range(rng.integers(0, 4)):
        cy, cx = rng.integers(8, size-8), rng.integers(8, size-8)
        r = rng.integers(2, 6)
        peak_T = rng.uniform(330, 420)
        ys, xs = np.indices((size, size))
        env = np.exp(-((ys-cy)**2 + (xs-cx)**2)/(2*r*r)).astype('f4')
        bt += env * (peak_T - 285)
        mask = np.maximum(mask, (env > 0.4).astype('f4'))
    return bt, mask

rng = np.random.default_rng(0)
train_X = np.stack([make_scene(rng=rng)[0] for _ in range(64)])
train_Y = np.stack([make_scene(rng=rng)[1] for _ in range(64)])
# Re-generate so X and Y match (we made them independently above — fix that)
pairs = [make_scene(rng=rng) for _ in range(64)]
train_X = np.stack([p[0] for p in pairs]); train_Y = np.stack([p[1] for p in pairs])
val_pairs = [make_scene(rng=rng) for _ in range(16)]
val_X = np.stack([p[0] for p in val_pairs]); val_Y = np.stack([p[1] for p in val_pairs])
print(f'Train: {train_X.shape} (BT) + {train_Y.shape} (mask)')
print(f'Val:   {val_X.shape}')
print(f'Positive-pixel fraction (train): {train_Y.mean()*100:.2f}%')"""))

cells.append(md("""## Step 2 — Tiny U-Net (~70k params)"""))
cells.append(code(
"""class TinyUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc1 = nn.Sequential(nn.Conv2d(1, 16, 3, padding=1), nn.ReLU())
        self.enc2 = nn.Sequential(nn.Conv2d(16, 32, 3, padding=1), nn.ReLU())
        self.pool = nn.MaxPool2d(2)
        self.bottle = nn.Sequential(nn.Conv2d(32, 64, 3, padding=1), nn.ReLU())
        self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False)
        self.dec2 = nn.Sequential(nn.Conv2d(64+32, 32, 3, padding=1), nn.ReLU())
        self.dec1 = nn.Sequential(nn.Conv2d(32+16, 16, 3, padding=1), nn.ReLU())
        self.out = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        b = self.bottle(self.pool(e2))
        d2 = self.dec2(torch.cat([self.up(b), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up(d2), e1], dim=1))
        return self.out(d1)  # logits

model = TinyUNet()
n_params = sum(p.numel() for p in model.parameters())
print(f'TinyUNet parameters: {n_params:,}')"""))

cells.append(md("""## Step 3 — Train (a few epochs is enough on synthetic data)"""))
cells.append(code(
"""# Normalize BT to ~[0,1] before feeding to model
def normalize(bt): return ((bt - 280) / 100).astype('f4')

X_t = torch.from_numpy(normalize(train_X)).unsqueeze(1)
Y_t = torch.from_numpy(train_Y).unsqueeze(1)
X_v = torch.from_numpy(normalize(val_X)).unsqueeze(1)
Y_v = torch.from_numpy(val_Y).unsqueeze(1)

opt = torch.optim.Adam(model.parameters(), lr=1e-3)
loss_fn = nn.BCEWithLogitsLoss()
batch = 8
for epoch in range(8):
    model.train()
    losses = []
    perm = torch.randperm(len(X_t))
    for i in range(0, len(X_t), batch):
        idx = perm[i:i+batch]
        opt.zero_grad()
        out = model(X_t[idx])
        loss = loss_fn(out, Y_t[idx])
        loss.backward(); opt.step()
        losses.append(loss.item())
    model.eval()
    with torch.no_grad():
        vloss = loss_fn(model(X_v), Y_v).item()
    print(f'epoch {epoch+1:>2}  train loss {np.mean(losses):.4f}  val loss {vloss:.4f}')"""))

cells.append(md("""## Step 4 — Compare U-Net to a threshold baseline"""))
cells.append(code(
"""# Predict on val set; compare to a global-threshold baseline
model.eval()
with torch.no_grad():
    pred = torch.sigmoid(model(X_v)).numpy()
pred_mask = (pred > 0.5).astype('f4')

threshold_mask = (val_X > 315).astype('f4')[:, None]  # naive global threshold

def iou(a, b):
    inter = ((a > 0.5) & (b > 0.5)).sum()
    union = ((a > 0.5) | (b > 0.5)).sum()
    return inter / max(union, 1)

ious_unet = [iou(pred_mask[i, 0], val_Y[i]) for i in range(len(val_Y))]
ious_thr  = [iou(threshold_mask[i, 0], val_Y[i]) for i in range(len(val_Y))]
print(f'Mean IoU on val:')
print(f'  threshold > 315 K:  {np.mean(ious_thr):.3f}')
print(f'  TinyUNet:           {np.mean(ious_unet):.3f}')
print(f'  improvement:        {(np.mean(ious_unet) - np.mean(ious_thr)) * 100:+.1f} points')"""))

cells.append(md(
"""## Step 5 — Visualize one prediction
"""))
cells.append(code(
"""import matplotlib.pyplot as plt
i = 2
fig, axes = plt.subplots(1, 4, figsize=(16, 4), dpi=110)
axes[0].imshow(val_X[i], cmap='inferno'); axes[0].set_title(f'BT scene #{i}')
axes[1].imshow(val_Y[i], cmap='gray');    axes[1].set_title('ground-truth mask')
axes[2].imshow(threshold_mask[i, 0], cmap='gray'); axes[2].set_title(f'threshold>315  IoU={ious_thr[i]:.2f}')
axes[3].imshow(pred_mask[i, 0], cmap='gray'); axes[3].set_title(f'TinyUNet  IoU={ious_unet[i]:.2f}')
for a in axes: a.set_xticks([]); a.set_yticks([])
plt.tight_layout(); plt.show()"""))

cells.append(md(
"""## Common gotchas

- **Mask imbalance.** Synthetic positive fraction is ~1-3% above; real-world is much worse. Use `BCEWithLogitsLoss(pos_weight=…)` to upweight the rare class, or focal loss.
- **Bad augmentation eats accuracy.** Random rotations of a thermal scene are fine; horizontal flips of an aerial scene are fine; horizontal flips of a *temporal* sequence are not.
- **Don't normalize at train if you don't normalize at inference.** Mismatched preprocessing is the #1 reason production models perform worse than reported.
- **Threshold > 315 K is dumb but useful.** Always keep a non-ML baseline available — it's the floor against which you measure ML's value-add. If your U-Net gives 0.6 IoU and the baseline gives 0.65, the U-Net is *worse*.
- **Real space-domain models train on segmentation-annotated public datasets** (e.g., NIST FIRES, NASA FIRMS labels, the GOES-R fire-detection algorithm validation set). Building one from scratch on synthetic data is fine for learning the architecture; production needs labeled real scenes.
"""))

cells.append(md(
"""## Self-check
- [ ] Tiny U-Net trains in 8 epochs without diverging (loss decreases).
- [ ] TinyUNet IoU > threshold-baseline IoU by ≥ 5 percentage points on val (synthetic data; real-world margin is usually smaller).
- [ ] Visualization renders four panels: BT, GT mask, threshold mask, U-Net mask.
- [ ] You can articulate when ML is worth it vs the simpler threshold (when ground truth is non-trivial — clouds, glint, parallax).
- [ ] Quiz on the [Week 22 page](https://launchdetect.com/academy/week/22/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-22/lab.ipynb ({len(cells)} cells)")
