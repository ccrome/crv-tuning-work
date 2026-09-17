# CR-V speed calibration

## Status

Implemented in the local `crv-sng-tuning` source branch; not yet installed or
validated on-road. The current stripped installer release does not yet contain
the matching compiled parameter registry, so the estimator safely operates
drive-locally there but cannot persist a learned value. A complete ARM prebuilt
release containing the updated `params_pyx` binary is required before
persistence can be enabled. The estimator is CR-V 5G-only and begins at a
neutral scale of `1.0` on a fresh device.

The current CR-V controller uses a high-rate CAN wheel/transmission speed
signal (`vEgo`). On this vehicle, that signal is consistently lower than the
Honda cluster speed at road speed. Consequently, a controller that appears to
hold its requested speed in `vEgo` can display 1–2 mph high on the Honda
instrument cluster.

## Evidence

The five local routes below were re-extracted with controller, raw,
cluster, and GPS-speed signals:

| Route | Segments | Cluster/controller scale |
|---|---:|---:|
| `00000002--8ced2f02b1` | 52 | 1.03637 |
| `00000003--290a49ad52` | 57 | 1.03630 |
| `00000009--e1324b27be` | 19 | 1.03532 |
| `0000005c--3c70bb383d` | 71 | 1.03630 |
| `0000005d--46b3832579` | 51 | 1.03685 |

Using valid controller speeds from 20–80 mph, the combined fit is:

```text
cluster_speed ~= 1.0360 * controller_speed + 0.02 mph
```

The intercept is negligible. The approximately 0.8 mph residual is consistent
with the cluster's 1 mph quantization, so the relationship is well represented
by a scale factor rather than a fixed mph offset or a speed-dependent curve.

Example from `00000009--e1324b27be` at route time 376 s:

| Signal | Speed |
|---|---:|
| Cruise setpoint | 69.59 mph |
| Controller speed (`vEgo`) | 69.15 mph |
| Honda cluster speed | 71.00 mph |
| GPS ground speed | 70.71 mph |

At that moment the controller believed it was slightly below the setpoint,
while the cluster and GPS showed that the vehicle was about 1 mph above it.

## Intended behavior

The requested speed should correspond to calibrated road speed as represented
by the Honda cluster. The control loop must continue to use a fast CAN speed
signal; GPS must not be used directly as a per-cycle feedback input.

```text
Honda cluster speed  -> slow calibration reference
Unscaled CAN speed   -> high-rate control measurement
Learned scale        -> calibrated vEgo for planning and longitudinal control
GPS speed            -> independent validation only
```

GPS validation across healthy fixes shows that the cluster is itself typically
about 0.9 mph above GPS ground speed. That is an expected display/reference
difference to monitor, not a signal that GPS should directly drive the
controller. Matching the cluster means a selected speed will match what the
driver sees on the Honda dash.

## Adaptive estimator implementation

The Honda vehicle interface now contains a CR-V-specific persistent estimator:

- Retain an unscaled wheel-speed measurement exclusively for estimation.
- Observe the Honda cluster speed only when it is valid, fresh, and above
  roughly 20 mph.
- Estimate a scale through the origin over accumulated samples; do not use an
  instantaneous ratio because the cluster is quantized.
- Apply the learned scale to the high-rate CAN speed before publishing `vEgo`
  to planning and longitudinal control.
- Never use the already-scaled published `vEgo` as the estimator input; that
  would make the estimator chase its own output.
- Use 30-second eligible-driving regression batches and a 30-minute eligible-
  driving time constant, with hard 0.98–1.06 bounds.
- Persist the estimate periodically rather than writing a parameter every
  control cycle.
- Log GPS-versus-cluster error for validation and flag sustained disagreement;
  do not use it to update the scale.

Once a matching prebuilt release is available, the learned value is stored in
the device-local persistent parameter `HondaCrvSpeedScale`. It is intentionally
not backed up, because calibration is specific to the vehicle/device
combination. Until then, an older prebuilt registry is detected safely and the
estimator remains in-memory for the current drive. The correction is blended
from 1.0 at 5 m/s to fully applied at 10 m/s, preserving the existing
low-speed stop-and-go behavior.

## Validation plan before deployment

1. Collect several more steady-speed drives at multiple speeds, tire states,
   temperatures, and road conditions.
2. Confirm cluster/controller scale remains multiplicative and within the
   proposed bounds for each drive.
3. Replay logs with the estimator to check convergence, startup
   behavior, and resistance to cluster quantization.
4. Test on-road with a fixed safe initial scale and a very slow adaptation
   rate, confirming that cluster speed matches the setpoint without introducing
   speed oscillation, unsafe following behavior, or discontinuities after
   reboot.
5. Keep GPS validation dashboards enabled to detect a changed cluster/ground
   relationship after tire or vehicle changes.
6. Before deployment, build a complete ARM prebuilt release from the full
   source tree and verify that its compiled `params_pyx` recognizes
   `HondaCrvSpeedScale`.
