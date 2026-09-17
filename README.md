# CR-V longitudinal tuning workspace

This repository collects the local analysis work for the 5th-generation Honda
CR-V: the Plotly/Streamlit log dashboard, interpretable plant model, tuning
artifacts, route split metadata, and operating procedures.

The SunnyPilot driving-code changes live in the sibling repository at
`../sunnypilot`, branch `crv-sng-tuning`. The current UI/profile change is
commit `9006867` (the later SunnyLink fix is developed there).

## Get route logs from the Comma

The Comma must have SSH enabled in its Developer settings. Find its current
LAN address from the computer, then set it explicitly:

```bash
export COMMA_HOST=192.168.86.31
export COMMA_SSH_KEY=/home/caleb/.ssh/id_rsa
ssh -i "$COMMA_SSH_KEY" comma@"$COMMA_HOST"
```

Copy complete routes by prefix. The script copies only `rlog.zst` and
`qlog.zst`, preserving the segment directories:

```bash
scripts/sync-comma-rlogs.sh 0000005e--0123456789
scripts/sync-comma-rlogs.sh --dry-run 0000005e--0123456789
```

The source on the Comma is `/data/media/0/realdata`; the default local
destination is `/home/caleb/openpilot/route-data`. Never commit that raw data
directory: it is large and may contain personally identifying location data.

If the device address changes, update `COMMA_HOST`. A public-key failure means
the SSH key is not authorized on the device; it is unrelated to route data.

## Analyze logs

From this repository:

```bash
/home/caleb/openpilot/log-dashboard/run-dashboard.sh
```

Or run extraction and Streamlit explicitly using the dashboard virtualenv:

```bash
PYTHONPATH=/home/caleb/openpilot/sunnypilot \
  /home/caleb/openpilot/.venv-log-dashboard/bin/python \
  dashboard/extract_logs.py

PYTHONPATH=/home/caleb/openpilot/sunnypilot \
  /home/caleb/openpilot/.venv-log-dashboard/bin/streamlit run dashboard/app.py
```

The dashboard uses Plotly, includes control inputs/outputs, event regions,
GPS/time-of-day hover data, and the route map. It reads local route data and
generated cache files; it does not upload logs.

## Plant model

The current model is a small, interpretable grey-box plant with separate gas,
coast, and brake response modes. Train it against the route split metadata:

```bash
cd plant-model
/home/caleb/openpilot/.venv-log-dashboard/bin/python fit.py --split training
/home/caleb/openpilot/.venv-log-dashboard/bin/python fit_closed_loop.py --split training
```

Keep complete drives together in one split. The current `5c` and `5d` drives
are training data; validation and test are intentionally empty until more
drives are collected.

## SunnyPilot tuning profiles

The CR-V profile selector is intended to be changed while parked, then applied
after the next offroad/onroad cycle:

- `default`: pre-experiment Bosch behavior
- `low_speed`: stop-and-go changes only
- `high_speed`: highway speed-tracking changes only
- `best_guess`: combined current first guess

The canonical SunnyPilot source and profile definitions are in
`../sunnypilot`. The persistent selector is
`HondaCrvLongitudinalTuningProfile`; the SSH helper in the SunnyPilot repo is:

```bash
cd /data/openpilot
python3 tools/crv_long_tune.py show
python3 tools/crv_long_tune.py load low_speed
```

On comma four, the setting is intended to be exposed through SunnyLink because
the C4 touchscreen has a simplified settings UI.

## Speed calibration

See [SPEED_CALIBRATION.md](SPEED_CALIBRATION.md) for the cross-route evidence
that Honda cluster speed is a stable multiplicative reference for the
controller-speed signal, along with the proposed bounded slow-adaptation
design and validation plan.

## Safety and experiment procedure

Run one profile per drive and record the profile, route, software commit, road
type, traffic conditions, and any disengagement. Start with the low-speed or
highway-isolation profile when diagnosing one behavior. Use `best_guess` only
after reviewing the isolated results. The driver remains responsible for the
vehicle at all times.
