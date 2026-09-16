"""Hybrid grey-box longitudinal plant model for the Honda CR-V."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


GAS_DEADBAND = 0.05
BRAKE_CROSSOVER = -0.15


@dataclass
class PlantParameters:
  gas_gain: float = 1.0
  gas_tau_s: float = 0.45
  gas_delay_s: float = 0.30
  brake_gain: float = 1.0
  brake_tau_s: float = 0.35
  brake_delay_s: float = 0.25
  coast_tau_s: float = 0.65
  drag_c0: float = 0.035
  drag_c1: float = 0.002
  drag_c2: float = 0.00035

  @classmethod
  def from_array(cls, values: np.ndarray) -> "PlantParameters":
    return cls(*map(float, values))

  def to_array(self) -> np.ndarray:
    return np.asarray(list(asdict(self).values()), dtype=float)


PARAMETER_NAMES = list(PlantParameters().__dict__.keys())
INITIAL_PARAMETERS = PlantParameters()
LOWER_BOUNDS = np.array([0.2, 0.05, 0.0, 0.2, 0.05, 0.0, 0.05, 0.0, 0.0, 0.0])
UPPER_BOUNDS = np.array([2.0, 3.0, 1.5, 2.0, 3.0, 1.5, 3.0, 0.8, 0.08, 0.003])


def mode_for_command(command: np.ndarray) -> np.ndarray:
  """0=coast, 1=gas, 2=brake."""
  mode = np.zeros(len(command), dtype=np.int8)
  mode[command > GAS_DEADBAND] = 1
  mode[command < BRAKE_CROSSOVER] = 2
  return mode


def delayed_command(time_s: np.ndarray, command: np.ndarray, delay_s: float) -> np.ndarray:
  return np.interp(time_s - delay_s, time_s, command, left=command[0], right=command[-1])


def predict_one_step(time_s: np.ndarray, speed_mps: np.ndarray, accel_mps2: np.ndarray,
                     command: np.ndarray, parameters: PlantParameters) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
  """Predict state at i+1 from observed state at i for a contiguous sequence."""
  gas_command = delayed_command(time_s, command, parameters.gas_delay_s)
  brake_command = delayed_command(time_s, command, parameters.brake_delay_s)
  mode = mode_for_command(command)
  delayed = np.where(mode == 1, gas_command, brake_command)
  tau = np.where(mode == 1, parameters.gas_tau_s,
                 np.where(mode == 2, parameters.brake_tau_s, parameters.coast_tau_s))
  gain = np.where(mode == 1, parameters.gas_gain,
                  np.where(mode == 2, parameters.brake_gain, 0.0))
  drag = parameters.drag_c0 + parameters.drag_c1 * speed_mps + parameters.drag_c2 * speed_mps ** 2
  target_accel = gain * delayed - drag
  dt = np.clip(np.diff(time_s, append=time_s[-1]), 0.02, 0.20)
  next_accel = accel_mps2 + (dt / tau) * (target_accel - accel_mps2)
  next_speed = np.maximum(0.0, speed_mps + dt * next_accel)
  return next_speed[:-1], next_accel[:-1], mode[:-1]


def rollout(time_s: np.ndarray, speed0_mps: float, accel0_mps2: float,
            command: np.ndarray, parameters: PlantParameters) -> tuple[np.ndarray, np.ndarray]:
  """Open-loop rollout over a contiguous command sequence."""
  gas_command = delayed_command(time_s, command, parameters.gas_delay_s)
  brake_command = delayed_command(time_s, command, parameters.brake_delay_s)
  mode = mode_for_command(command)
  speed = np.empty(len(time_s), dtype=float)
  accel = np.empty(len(time_s), dtype=float)
  speed[0], accel[0] = speed0_mps, accel0_mps2
  for i in range(len(time_s) - 1):
    delayed = gas_command[i] if mode[i] == 1 else brake_command[i]
    tau = parameters.gas_tau_s if mode[i] == 1 else parameters.brake_tau_s if mode[i] == 2 else parameters.coast_tau_s
    gain = parameters.gas_gain if mode[i] == 1 else parameters.brake_gain if mode[i] == 2 else 0.0
    drag = parameters.drag_c0 + parameters.drag_c1 * speed[i] + parameters.drag_c2 * speed[i] ** 2
    target_accel = gain * delayed - drag
    dt = float(np.clip(time_s[i + 1] - time_s[i], 0.02, 0.20))
    accel[i + 1] = accel[i] + dt / tau * (target_accel - accel[i])
    speed[i + 1] = max(0.0, speed[i] + dt * accel[i + 1])
  return speed, accel
