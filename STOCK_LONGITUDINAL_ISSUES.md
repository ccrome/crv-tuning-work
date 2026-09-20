# CR-V stock longitudinal-control issue checklist

This is the current baseline checklist for the installed stock-longitudinal
build. Brake-hold engagement protection and cluster-speed calibration are
already installed and are deliberately excluded. Each item needs an isolated
fix and a passing automated check before an on-road trial.

## L1 — credible closing lead can lose braking after a brief tracker loss

- Status: confirmed; highest priority.
- Evidence: baseline route `0000005c--3c70bb383d`, approximately 640–710 s,
  has 56 source changes among `lead0`, `lead1`, and `cruise`. Commands range
  from `-2.36` to `+0.80 m/s²` while the model lead is as close as `1.04 m`.
- Reproductions: a `12 m` slower lead at `7.0 m/s`, and the route-22-like
  32 mph / 16 m / `-2.3 m/s` closing-lead case. Both drop tracker candidates
  for 0.5 seconds while cruise remains set.
- Required outcome: when a recently credible lead was close and closing, do
  not authorize positive acceleration merely because tracker candidates vanish.
- Automated check: `test_crv_brief_tracker_loss_regression.py`. The low-speed
  case passes with the installed initial guard; the moderate-speed case remains
  an expected failure until that guard is generalized.

## L2 — stopped or near-stopped following can resume with too little margin

- Status: confirmed observation; root cause overlaps L1 but needs a separate
  stop-release test.
- Evidence: route 5c has ten stopped-following episodes; valid model-lead
  distances have a `1.04 m` minimum and `2.78 m` median. On route 1e around
  2808 s, output becomes positive near a `2.7 m` gap and the CR-V accelerates
  past 20 mph while the estimated gap remains under about `8 m`.
- Required outcome: stop release must retain a conservative gap and must not
  resume toward a close, closing lead.
- Automated check: `test_crv_stop_release_regression.py`. The focused L2 hold
  is in draft PR #7 and must receive isolated low-speed on-road validation.

## L3 — some high-speed tracked-lead approaches brake too late

- Status: driver-reported and log-supported; lead validity must be checked per
  event before changing control logic.
- Evidence: route 1e around 1974–1994 s was driver-marked after an approach
  from about 72 mph toward a lead closing at roughly `4.3 m/s`; the driver
  braked near 63 mph and about 26 m.
- Required outcome: a credible close, rapidly closing lead must constrain
  acceleration early enough without reacting to one-sample tracker noise.
- Automated check: `dashboard/test_high_speed_braking_regression.py` evaluates
  the documented pre-takeover window. It remains a log-backed expected failure.

## L4 — steady no-lead highway speed oscillates and overshoots

- Status: confirmed; separate from lead-following safety.
- Evidence: stock baseline no-lead, stable-set-speed windows reach `4.07 mph`
  peak-to-peak variation on route 5c and `4.30 mph` on route 5d. Maximum
  overshoot is `+2.63 mph` and `+2.26 mph`; broader reviewed windows reach
  about `5.6–8.5 mph` peak-to-peak.
- Likely contributors: feedforward-dominated control (logged Bosch integral
  gains are zero) and observed `0.7–1.6 s` command-to-acceleration lag versus
  the configured `0.5 s` delay.
- Required outcome: improve steady-speed regulation without changing
  close-lead or stop-release behavior.
- Next test: a no-lead fixed-set-speed maneuver with fixed delay, duration,
  overshoot, peak-to-peak speed, and jerk limits.

## Rules for the next change

1. Fix one checklist item at a time; do not combine safety guards, delay
   calibration, following-distance changes, and Honda actuator-mode changes.
2. Convert its deterministic regression from stock failure to a required pass.
3. Run the longitudinal maneuver suite, then build only after tests pass.
4. On road, collect a complete route with bookmarks and compare it to the
   stock baseline in `TUNING_LOG.md`.
5. Reject a change if it adds surge/chatter, increases jerk materially, or
   makes another checklist item worse.
