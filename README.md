# LaunchDetect Academy — Lab Notebooks

Companion lab notebooks for **[LaunchDetect Academy](https://launchdetect.com/academy/)**, a free 30-week course in space-domain geographic information systems.

## Structure

```
week-01/  lab.ipynb     # Week 1 starting scaffold
week-02/  lab.ipynb     # Week 2
...
week-30/  lab.ipynb     # Week 30
capstones/
  01-launch-site-atlas/      capstone.ipynb
  02-coverage-tool/          capstone.ipynb
  03-plume-detector/         capstone.ipynb
  04-realtime-tracker/       capstone.ipynb
  05-end-to-end-pipeline/    capstone.ipynb
```

Each week page links into the matching notebook here. Click the "Open in Colab" button on any week page to launch directly in Google Colab — no install required.

## How to use

**In Colab** (recommended for fast start):
Visit any week page on [launchdetect.com/academy/](https://launchdetect.com/academy/) and click **Open in Colab**. The notebook loads, dependencies install, and you can edit + run in your browser. Your changes save to your own Google Drive copy.

**Locally** (recommended for serious work):
```bash
git clone https://github.com/launchdetect/academy-labs
cd academy-labs
pip install -r requirements.txt  # if present, or install per-week deps as needed
jupyter lab
```

## Contributing

PRs welcome. Especially valued:
- Reference solutions for the lab stubs
- Sample datasets that demonstrate edge cases
- Corrections to inaccurate claims or broken code

Open an issue first for non-trivial additions so we can align on scope.

## License

MIT — see `LICENSE`. Use these notebooks freely for self-study, teaching, or commercial work.
