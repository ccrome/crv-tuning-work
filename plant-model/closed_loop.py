"""Small closed-loop longitudinal simulator built around :mod:`plant`.

This is deliberately a controller-identification and reference-replay tool, not
a replacement for Sunnypilot's planner.  It receives the logged plan speed and
acceleration as an exogenous reference, then closes the loop through the fitted
vehicle plant.  That lets us test whether controller-gain changes are stable
before touching on-road tuning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from plant import PlantParameters, mode_for_command


@dataclass
class ControllerParameters:
  kp: float = 0.18
  ki: float = 0.025
  kff: float = 1.0
  command_tau_s: float = 0.20
  integral_limit: float = 15.0

  @classmethod
  def from_array(cls, values: np.ndarray) -> "ControllerParameters":
    return cls(*map(float, values))

  def to_array(self) -> np.ndarray:
    return np.asarray(list(asdict(self).values()), dtype=float)


CONTROLLER_PARAMETER_NAMES = list(ControllerParameters().__dict__.keys())
CONTROLLER_INITIAL = ControllerParameters()
CONTROLLER_LOWER = np.array([0.0, 0.0, 0.0, 0.02, 1.0])
CONTROLLER_UPPER = np.array([2.0, 0.8, 2.0, 2.0, 40.0])


def controller_command(speed_error: np.ndarray, plan_accel: np.ndarray,
                       time_s: np.ndarray, parameters: ControllerParameters) -> np.ndarray:
  """Controller output evaluated on observed vehicle state for identification."""
  dt = np.clip(np.diff(time_s, prepend=time_s[0]), 0.0, 0.20)
  integral = np.clip(np.cumsum(speed_error * dt), -parameters.integral_limit, parameters.integral_limit)
  raw = parameters.kp * speed_error + parameters.ki * integral + parameters.kff * plan_accel
  output = np.empty(len(raw), dtype=float)
  output[0] = np.clip(raw[0], -3.5, 2.5)
  for i in range(len(raw) - 1):
    output[i + 1] = output[i] + dt[i + 1] / parameters.command_tau_s * (raw[i] - output[i])
    output[i + 1] = np.clip(output[i + 1], -3.5, 2.5)
  return output


def simulate_reference_replay(time_s: np.ndarray, reference_speed_mps: np.ndarray,
                              reference_accel_mps2: np.ndarray, speed0_mps: float,
                              accel0_mps2: float, plant: PlantParameters,
                              controller: ControllerParameters) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
  """Run controller and plant together against a fixed recorded reference."""
  n = len(time_s)
  speed = np.empty(n, dtype=float)
  accel = np.empty(n, dtype=float)
  command = np.empty(n, dtype=float)
  speed[0], accel[0] = speed0_mps, accel0_mps2
  integral = 0.0
  command[0] = np.clip(controller.kp * (reference_speed_mps[0] - speed[0]) +
                       controller.kff * reference_accel_mps2[0], -3.5, 2.5)
  # The plant delay belongs inside this causal loop.  Store commands and use
  # timestamp interpolation only over the past command history.
  for i in range(n - 1):
    dt = float(np.clip(time_s[i + 1] - time_s[i], 0.02, 0.20))
    error = reference_speed_mps[i] - speed[i]
    integral = float(np.clip(integral + error * dt, -controller.integral_limit, controller.integral_limit))
    raw = controller.kp * error + controller.ki * integral + controller.kff * reference_accel_mps2[i]
    next_command = command[i] + dt / controller.command_tau_s * (raw - command[i])
    command[i + 1] = float(np.clip(next_command, -3.5, 2.5))

    mode = int(mode_for_command(np.asarray([command[i]]))[0])
    delay = plant.gas_delay_s if mode == 1 else plant.brake_delay_s
    delayed_command = float(np.interp(time_s[i] - delay, time_s[:i + 1], command[:i + 1], left=command[0]))
    tau = plant.gas_tau_s if mode == 1 else plant.brake_tau_s if mode == 2 else plant.coast_tau_s
    gain = plant.gas_gain if mode == 1 else plant.brake_gain if mode == 2 else 0.0
    drag = plant.drag_c0 + plant.drag_c1 * speed[i] + plant.drag_c2 * speed[i] ** 2
    target_accel = gain * delayed_command - drag
    accel[i + 1] = accel[i] + dt / tau * (target_accel - accel[i])
    speed[i + 1] = max(0.0, speed[i] + dt * accel[i + 1])
  return speed, accel, command
