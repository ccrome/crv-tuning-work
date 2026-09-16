# Findings from routes 0000005c and 0000005d

Both routes are from a Honda CR-V 5G running sunnypilot 2026.002.002,
`release-mici` commit `6a17f75c`. They predate the local brake-crossover
hysteresis patch and provide a baseline.

## Stop-and-go

- Route `0000005c` contains the strongest example: 57 gas-to-brake transitions
  below 8 m/s, including 39 below 5 m/s.
- Ten distinct stopped-following episodes were found on that route. Their
  median final model-lead distance was 2.69 m; the closest sample was 1.04 m.
  The MPC steady-state target at a stop is 6.0 m.
- Route `0000005d` had five stopped-following episodes. Their median distance
  was 4.74 m and the closest sample was 2.63 m.
- In the worst event (route `0000005c`, approximately 10.8–11.7 minutes), the
  selected source repeatedly changes between `lead0/lead1` and `cruise` while
  lead distance jumps. The controller responds with positive acceleration,
  then braking up to roughly -2.3 m/s². The vehicle stops around 1.4 m behind
  the model lead.

The stock -0.20 m/s² Bosch gas/brake boundary amplifies this behavior, but the
initiating problem is unstable lead/source selection. Hysteresis should reduce
CAN gas/brake chatter; it cannot by itself restore the missing stopping margin.

## Highway

- Near stable cruise setpoints, observed overshoot reaches approximately
  +2.5 to +3.2 mph.
- Sustained windows show roughly 5.6–8.5 mph peak-to-peak speed variation, with
  common periods around 10–25 seconds.
- The Bosch CR-V longitudinal PID gains in these logs are all zero. Controller
  output is therefore almost pure planner feedforward.
- In the cleanest highway windows, command-to-measured-acceleration lag is
  commonly about 0.7–1.6 seconds, while `longitudinalActuatorDelay` is 0.5 s.

## Suggested controlled experiments

1. Retain the CR-V low-speed crossover hysteresis (-0.15 m/s² to enter braking,
   -0.05 m/s² to leave braking, below 5 m/s) and collect another matched route.
2. Test a CR-V-specific standstill margin of roughly +2.5 m (8.5 m total), not
   a global `STOP_DISTANCE` change. Verify model-lead distance against video.
3. Test `longitudinalActuatorDelay = 0.8 s` before adding feedback gains. If the
   highway oscillation remains, evaluate small Bosch acceleration-feedback
   gains in a separate experiment rather than changing delay and gains at once.

These values are starting points for A/B testing, not final safety-validated
calibration values.
