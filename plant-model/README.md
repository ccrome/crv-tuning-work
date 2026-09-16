# CR-V longitudinal plant model

This is the first, intentionally interpretable model of the CR-V longitudinal
plant. It predicts the next vehicle acceleration and speed from the controller's
acceleration command and the current vehicle state.

It is a moving-vehicle, hybrid grey-box model with three modes:

- **gas**: positive acceleration command
- **coast**: command inside the gas/brake deadband
- **brake**: negative acceleration command beyond the brake crossover

Gas and brake have separate actuator delays; all three modes have their own
first-order response time constant. A speed-dependent coastdown term represents
rolling and aerodynamic resistance.
Standstill hold, launch, road grade, and driver overrides are deliberately
excluded from this baseline and will be added as separate modes.

## Inputs and outputs

Inputs are `carOutput.actuatorsOutput.accel` (the Honda longitudinal command),
current speed, and recent command history. Outputs are next-step `aEgo` and
`vEgo`. The model does not use set speed, planner output, lead distance, or
future state: those belong upstream of the plant.

## Train

The route assignments come from `../route-data-splits/index.csv`. The initial
training split contains both currently available drives.

```bash
../.venv-log-dashboard/bin/python fit.py --split training
```

Artifacts are written to `artifacts/`:

- `plant_model.json` — fitted parameters
- `training_report.json` — fit and rollout metrics

## Model equation

For the delayed command `u(t-d_m)` and mode `m`:

```text
a_target = gain_m * u(t-d_m) - (c0 + c1*v + c2*v^2)
a_next   = a + dt/tau_m * (a_target - a)
v_next   = v + dt*a_next
```

The parameters are estimated with robust nonlinear least squares. This baseline
is meant to reveal whether delay, gain, or coastdown mismatch is driving the
observed closed-loop oscillations before introducing any learned residual model.

## Closed-loop reference replay

After fitting the plant, fit the small PI + feedforward controller and run it
against each logged `longitudinalPlan` reference:

```bash
../.venv-log-dashboard/bin/python fit_closed_loop.py --split training
```

This is a closed-loop *reference-replay* simulation: the controller sees the
current logged planned speed/acceleration and the simulator's current plant
state, then commands the fitted plant. It is not an on-road controller and it
does not replace SunnyPilot's planner. Its artifacts are:

- `artifacts/closed_loop_model.json` — fitted controller parameters
- `artifacts/closed_loop_training_report.json` — tracking and command-fit metrics
