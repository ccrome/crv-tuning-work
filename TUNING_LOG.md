# CR-V longitudinal tuning log

This is the canonical record of each longitudinal experiment. Record the exact
software commit and complete routes before judging a change. Change one control
idea at a time whenever possible; brake hold and cluster-speed calibration are
tracked separately and are not longitudinal tuning variables.

## Measurement rules

- Compare complete drives against the stock baseline routes below.
- Record both driver observations and objective log measurements.
- Treat isolated radar samples as suspect. Confirm safety-relevant behavior
  across adjacent samples and through radar, planner, controller, CAN output,
  vehicle response, and driver-pedal signals.
- A UI bookmark marks the driver's observation time, which can follow the
  beginning of the behavior. Review at least 15 seconds on both sides.
- Do not combine unrelated planner, controller, actuator-mode, or following-gap
  changes in one experiment.

## Baseline S0 — stock SunnyPilot longitudinal control

Status: active baseline, restored and installed on 2026-09-19.

- Software: SunnyPilot `release-mici` `6a17f75c6bcb67c85f252a1acc342d94d5b8a4d2`
- Rollback source commit: `dc1b7d7e6f8fecaaa9d413d45b4acb997f242d23`
- Installed native release: `b9f77ff5984c429ca6cd63c6e3229c5aae77f5b3`
- Retained non-tuning changes: brake-hold engagement protection and CR-V
  cluster-speed calibration
- Vehicle: `HONDA_CRV_5G`
- Longitudinal actuator delay: `0.5 s`
- Logged personality: `relaxed`
- CR-V-specific longitudinal changes: none
- Routes:
  - `0000005c--3c70bb383d` (71 segments, 70.6 minutes)
  - `0000005d--46b3832579` (51 segments, 50.5 minutes)
- UI bookmarks: none in either route

Observed low-speed problems:

- Route 5c contains ten stopped-following episodes. Across valid standstill
  samples, model-lead distance reached `1.04 m` and had a `2.78 m` median.
- Route 5d contains five stopped-following episodes. Valid standstill samples
  reached `2.63 m` and had a `4.77 m` median.
- In route 5c at approximately `t=640–710 s`, the selected planner source
  changed 56 times among `lead0`, `lead1`, and `cruise`. The outgoing command
  ranged from `-2.36` to `+0.80 m/s²`; the vehicle stopped about `1.04 m` from
  the model lead and then launched as the source changed again.
- The stock `-0.20 m/s²` Honda gas/brake crossover amplifies the resulting
  command changes, but it does not initiate the lead/source instability.

Observed highway problems:

- The logged Bosch CR-V integral gains were zero, leaving acceleration control
  dominated by planner feedforward.
- In strict 30-second, no-lead, stable-set-speed windows, peak-to-peak speed
  variation reached `4.07 mph` on route 5c and `4.30 mph` on route 5d.
- Maximum overshoot in those strict windows was `+2.63 mph` and `+2.26 mph`,
  respectively. Broader previously reviewed cruise windows showed roughly
  `5.6–8.5 mph` peak-to-peak variation over 10–25 second periods.
- Measured command-to-acceleration lag was commonly `0.7–1.6 s`, longer than
  the configured `0.5 s` actuator delay.

Baseline diagnosis:

1. Low speed: unstable lead/source selection can release braking or authorize
   acceleration at an inadequate gap.
2. Highway: stock delay/feedforward calibration produces speed oscillation and
   overshoot.
3. These are separate problems and should be tested separately.

## Regression test LSR1 — close, closing lead-source dropout

Status: added; expected failure on stock until a focused safety fix exists.

- Source commit: `b6f9abe52e` (stacked on the brake-hold branch)
- Draft PR: https://github.com/ccrome/sunnypilot/pull/4
- Test: `openpilot/selfdrive/test/longitudinal_maneuvers/test_crv_lead_source_regression.py`
- Setup: establish a slower lead at `12 m` while traveling at `7.0 m/s`, then
  remove both tracker candidates for 0.5 seconds while cruise remains set.
- Requirement: while the lead remains within `11 m` and closing faster than
  `1.0 m/s`, planner output must not become positive merely because the lead
  source changes to cruise.
- Current stock result: expected failure. It switches to cruise and reaches
  approximately `+1.26 m/s²` while the gap is below `10 m`.
- Test command:

  ```bash
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_lead_source_regression
  ```

The expected-failure decorator must be removed when implementing the safety
fix. At that point, the test becomes a required normal pass and an unexpected
success before that change remains visible to CI.

## Experiment LSR2 — CR-V close-lead dropout hold

Status: native release built and ready to update; not road-tested.

- Source commit: `2b89b2babd`
- Draft PR: https://github.com/ccrome/sunnypilot/pull/5 (stacked on LSR1)
- Native release: `315f2d0dfc97d9a3957f622ad3ce7ce4698f01b8`
- Scope: only `HONDA_CRV_5G`; it has no parameter, UI setting, personality,
  following-distance, experimental-mode, or Honda gas/brake crossover change.
- Behavior: after a credible lead is closer than `11 m` and closing faster than
  `1.0 m/s`, a loss of both radar lead candidates starts a `0.5 s` hold. During
  that hold, output cannot exceed zero and is released from the prior braking
  command at no more than `1.0 m/s³`.
- Test change: LSR1 is now a normal required pass, using an explicitly enabled
  CR-V stock-longitudinal simulation rather than an expected failure.
- Validation:

  ```bash
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_lead_source_regression
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_longitudinal
  .venv/bin/ruff check \
    openpilot/selfdrive/controls/lib/longitudinal_planner.py \
    openpilot/selfdrive/test/longitudinal_maneuvers/plant.py \
    openpilot/selfdrive/test/longitudinal_maneuvers/test_crv_lead_source_regression.py
  ```

On-road acceptance: test a low-speed close-following route with bookmarks;
confirm no release toward a close, closing lead and no new harsh hold/release
feel. Compare jerk, stop gap, and source changes against S0.

### LSR2-R1 — first on-road validation routes

Status: release confirmed; patch trigger not observed, so efficacy remains
unproven on road.

- Native release: `315f2d0dfc97d9a3957f622ad3ce7ce4698f01b8`
- Routes: `00000004--0a2432880c` (11.4 min) and
  `00000005--e710b97a54` (11.5 min), both on `crv-sng-tuning` with the stock
  schema and `0.5 s` actuator delay.
- Bookmarks: none.
- Route 4: 50 engaged samples with a seen lead closer than `11 m` and closing
  faster than `1.0 m/s`; no positive planner target occurred in those samples.
  The observed approach ran from roughly `10.9 m` to `5.0 m` while braking.
- Route 5: no engaged close-and-closing lead samples.
- Trigger check: neither route lost both radar lead candidates within 0.5 s of
  a close-and-closing lead. Therefore neither route exercised the new hold.
- Verdict: no regression seen in these routes, but do not claim the patch
  worked on road yet. A deliberately bookmarked low-speed lead-loss/reacquire
  event is still needed.

## Regression test SR1 — close stopped-lead release

Status: added; expected failure on the current release until a focused
stop-release safety fix exists.

- Source commit: `b75959fafb` (stacked on LSR2)
- Draft PR: https://github.com/ccrome/sunnypilot/pull/6
- Evidence: baseline route `0000001e--2d841e7d0b`, approximately 2808 s. After
  a long stop with a lead near `2.7 m`, outgoing acceleration changes from
  braking to positive and the CR-V accelerates while the gap remains below
  about `8 m`.
- Test: `openpilot/selfdrive/test/longitudinal_maneuvers/test_crv_stop_release_regression.py`
- Setup: stop the CR-V `2.7 m` behind a stopped lead, establish that lead for
  one second, then remove both tracker candidates for 0.5 seconds while cruise
  stays set.
- Current result: expected failure. Stock immediately commands approximately
  `+1.6 m/s²` and begins moving toward the unseen physical lead.
- Requirement: while the remembered stopped lead remains within `3 m`, a
  tracker dropout must not authorize restart acceleration.
- Validation command:

  ```bash
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_stop_release_regression
  ```

The expected-failure decorator must be removed only when the focused L2 fix is
implemented and this becomes a normal required pass.

## Experiment SR2 — close stopped-lead dropout hold

Status: implemented and simulation-validated; not built, installed, or
road-tested.

- Source commit: `b8aed862d2`
- Draft PR: https://github.com/ccrome/sunnypilot/pull/7 (stacked on SR1)
- Scope: `HONDA_CRV_5G` only. No runtime option, following-distance,
  experimental-mode, Honda actuator-crossover, or speed-regulation change.
- Behavior: after confirming a stopped lead within `3 m` while the CR-V is
  essentially stopped, loss of both radar candidates starts a `0.5 s` hold.
  The planner caps acceleration at zero and keeps `shouldStop` true for that
  interval.
- Test change: SR1 is now a normal required pass and verifies both no restart
  acceleration and retained `shouldStop` during the loss.
- Validation:

  ```bash
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_stop_release_regression \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_lead_source_regression
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_longitudinal
  ```

On-road acceptance: make an ordinary low-speed stop behind traffic and bookmark
any release, surge, or harsh hold. A pass is no restart into a nearby stopped
lead and no new awkward hold/release feel. Do not combine this drive with a
speed-regulation experiment.

## Regression test SRG1 — no-lead speed regulation

Status: added; expected failure on the logged baseline. This is a log-backed
measurement, not a source-only plant test, because the simplified plant does
not reproduce the CR-V's real actuator dynamics.

- Test: `dashboard/test_speed_regulation_regression.py`
- Window rules: 30 seconds, longitudinal active, no radar lead, planner source
  `cruise`, fixed set speed, no driver gas/brake, and speed error no larger than
  `2 mph` before calculating variation.
- Limits: at most `1.0 mph` peak-to-peak variation and `+0.5 mph` overshoot.
- Highway stock evidence: routes `0000005c--3c70bb383d` and
  `0000005d--46b3832579`, set roughly 65–70 mph. The strict windows reach
  about `3.40 mph` peak-to-peak, so the highway test is an expected failure.
- Moderate-speed evidence: patched-release routes `00000004--0a2432880c` and
  `00000005--e710b97a54`, set roughly 30–35 mph. The strict windows reach
  about `1.92 mph` peak-to-peak, so the moderate-speed test is an expected
  failure too.
- Validation command:

  ```bash
  python -m unittest dashboard.test_speed_regulation_regression
  ```

For a speed-regulation experiment, collect matched no-lead routes at both speed
bands, replace the baseline route IDs, and remove the expected-failure markers.
Do not combine this with lead-following or stop-release changes.

## Regression tests L3 — credible closing-lead protection

Status: added; both checks are expected failures pending a focused L3 fix.

- Moderate-speed source test: draft PR https://github.com/ccrome/sunnypilot/pull/8
  (source commit `e633aa0ff4`),
  `test_crv_closing_lead_regression.py`.
  It reproduces route 22 around 904 s: 32 mph, a 16 m lead, and roughly
  `-2.3 m/s` closing rate. After lead-source loss, current behavior becomes
  positively accelerated while the unseen physical lead remains close.
- Higher-speed log test: `dashboard/test_high_speed_braking_regression.py`.
  It reproduces the route-1e driver-marked 1974--1975 s approach: about 72 mph,
  35--45 m gap, and roughly `-4.3 m/s` closing rate. Before driver braking,
  the logged outgoing command reaches only about `-0.99 m/s²`, below the
  provisional `-1.2 m/s²` threshold.
- These are intentionally separate: the moderate case can become a normal
  source test after a planner guard; the high-speed case needs matched on-road
  evidence before a code change can be called successful.
- Validation commands:

  ```bash
  .venv/bin/python -m unittest \
    openpilot.selfdrive.test.longitudinal_maneuvers.test_crv_closing_lead_regression
  python -m unittest dashboard.test_high_speed_braking_regression
  ```

## Experiment BG1 — “best guess v1”

Status: incomplete evidence; not suitable as a final comparison.

- Software commit: `1ac757a52977df6ed4276c42f1b77be9e5f0e229`
- Route: `00000009--e1324b27be` (19 segments)
- Conditions: highway and around-town driving; no stop-and-go
- Driver report: felt better overall and following seemed good, but settled
  roughly 1–2 mph above the Honda cluster set speed.
- Limitation: because the drive had no stop-and-go, it did not test the most
  important stock low-speed failure.

## Experiment S1 — `safeV1`

Status: rejected; do not use for further driving.

- Source commit: `0f5d594888ff85316d49237d17d3936749609402`
- Native release commit: `1233f9089c7e512545a5b38ccc4bc0a1b142a812`
- Route: `00000003--a8808762fc` (10 segments, 9.3 minutes)
- Fixed configuration: `0.8 s` actuator delay, zero integral gain, relaxed
  personality (`1.75 s` following time), global CR-V gas/coast/brake
  hysteresis, low-speed launch ceiling, stop latch, and closing-lead guard.
- UI bookmarks: none

Observed effects:

- Gas/coast/brake mode changed about 24 times per minute, versus roughly 6–11
  times per minute on the earlier comparison drives.
- In the weak-command range from `-0.15` to `-0.05 m/s²`, brake mode produced
  median actual deceleration of `-0.287 m/s²`; coast produced `-0.061 m/s²`.
  This discontinuity caused visible surging and chatter.
- Moving absolute jerk at the 95th percentile rose to `4.71 m/s³`, versus
  approximately `3.0–3.4 m/s³` on earlier drives.
- Moving acceleration's 5th–95th percentile range widened to approximately
  `-1.31` to `+1.65 m/s²`.
- Automated launches repeatedly reached `2.05–2.34 m/s²` even though the
  planner-side launch ceiling was `0.8 m/s²`; the ceiling did not represent
  the Honda actuator response.
- Forcing relaxed personality made “no runtime selection” mean a permanently
  long following profile rather than stock behavior.

Conclusion: S1 combined too many changes, introduced a severe actuator-mode
discontinuity, and did not provide an interpretable test of either original
stock problem. It is being reverted as a whole.

## Next experiment

Start from S0 behavior. Before another on-road tuning build, choose exactly one
of these scopes and define its pass/fail metrics:

1. Low-speed lead/source stability and stop-release margin, tested against the
   route-5c `t=640–710 s` regression window.
2. Highway speed regulation, tested only in no-lead stable-set-speed windows.

For every new experiment, append: experiment ID, hypothesis, exact code delta,
source and release commits, parameter values, routes/conditions, bookmarks,
objective measurements, driver report, regressions, and verdict.
