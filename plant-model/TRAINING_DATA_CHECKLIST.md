# Longitudinal plant-model training-data checklist

Collect routes only when it is safe and legal to do so. Keep the raw rlogs and
qlogs together, assign each complete drive to one split, and record the vehicle
configuration used for that drive.

## Split discipline

- [ ] Assign a whole drive to `training`, `validation`, or `test` before fitting.
- [ ] Never put segments from the same drive in more than one split.
- [ ] Reserve at least several complete, representative drives for validation and
  keep the test drives untouched until a candidate tune is chosen.
- [ ] Include routes from different days, traffic conditions, road grades, and
  temperatures in every eventual split.
- [ ] Note tire condition/pressure, passenger/cargo load, and any changes to
  longitudinal tuning or the gas/brake crossover.
- [ ] Record weather, road surface condition, and approximate outside temperature.

## Steady-state and coastdown data

- [ ] Several 30–60 second steady-speed intervals at approximately 20, 35, 50,
  65, and 75 mph on level road.
- [ ] At each practical speed, include a coastdown: release longitudinal command
  and let the car decelerate without a lead vehicle influencing control.
- [ ] Include both gentle uphill and downhill steady-speed/coastdown intervals.
- [ ] Include at least one route with substantial elevation change.

## Gas-response data

- [ ] Repeated small positive command steps at low, medium, and highway speeds.
- [ ] Positive command ramps, holds, and releases long enough to expose actuator
  delay and settling time.
- [ ] Near-setpoint highway behavior: approach the set speed from below and above.
- [ ] Cruise setpoint steps of roughly 2–5 mph where safe.
- [ ] Examples spanning the gas deadband and low-speed gas/brake crossover.

## Brake-response data

- [ ] Repeated gentle negative command steps at low, medium, and highway speeds.
- [ ] Brake ramps, holds, and releases to identify brake gain, delay, and lag.
- [ ] Controlled approach-to-stop events with a stable lead vehicle.
- [ ] Release/reapply transitions around the Bosch brake crossover.
- [ ] Samples where the car is decelerating downhill and uphill.

## Stop-and-go and standstill

- [ ] Multiple normal queue-following episodes with a stable lead.
- [ ] Lead starts moving after a full stop; capture launch delay and launch gain.
- [ ] Short and long stops, including brake-hold behavior.
- [ ] Different initial following distances and lead acceleration profiles.
- [ ] Clean examples with no driver pedal override.
- [ ] Separately label any uncomfortable, unsafe, or anomalous episode rather
  than treating it as typical plant behavior.

## Highway following and no-lead behavior

- [ ] No-lead cruise sections at several set speeds.
- [ ] Long no-lead sections crossing small grades to expose speed-hold drift.
- [ ] Stable lead-following at multiple distances and relative speeds.
- [ ] Lead appearance/disappearance examples, kept separate from pure plant
  identification because they exercise planner behavior too.
- [ ] Highway speed-overshoot and settling examples after setpoint changes.

## Data quality checks before fitting

- [ ] GPS has a valid fix; reject acquisition and impossible-jump points.
- [ ] Check timestamp continuity and exclude corrupt or missing intervals.
- [ ] Exclude driver gas/brake overrides from automated-plant fitting, but retain
  them as separately labeled examples.
- [ ] Verify `sendcan` command timestamps are correctly aligned with `carState`.
- [ ] Inspect signal units, saturation, and CAN-counter dropouts.
- [ ] Balance gas, coast, brake, launch, and stop samples; ordinary cruise alone
  is not sufficient.

## Minimum next collection target

- [ ] 5–10 additional complete drives before making tuning decisions from the model.
- [ ] At least two drives reserved for validation and two for final test.
- [ ] At least 10 clean examples each of: gas step, brake step, coastdown,
  stop/hold/relaunch, no-lead cruise recovery, and highway setpoint change.
