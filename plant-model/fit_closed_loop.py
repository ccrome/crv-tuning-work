#!/usr/bin/env python3
"""Train and evaluate the compact closed-loop reference-replay model."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from closed_loop import (CONTROLLER_INITIAL, CONTROLLER_LOWER, CONTROLLER_PARAMETER_NAMES,
                         CONTROLLER_UPPER, ControllerParameters, controller_command,
                         simulate_reference_replay)
from fit import load_sequences, routes_for_split
from plant import PlantParameters


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def load_controller_sequences(routes: list[str], stride: int = 2) -> list[tuple[str, pd.DataFrame]]:
  """Only retain causal planner/controller samples with a usable reference."""
  sequences = []
  cache = ROOT.parent / "log-dashboard" / "cache"
  columns = ["time", "v_ego", "a_ego", "accel_output", "plan_speed", "plan_accel",
             "long_active", "gas_pressed", "brake_pressed"]
  for route in routes:
    frame = pd.read_parquet(cache / f"{route}.parquet", columns=columns).dropna()
    valid = (frame.long_active.astype(bool) & ~frame.gas_pressed.astype(bool) &
             ~frame.brake_pressed.astype(bool) & (frame.v_ego >= 1.5) &
             frame.accel_output.between(-3.5, 2.5) & frame.plan_speed.between(0.0, 50.0) &
             frame.plan_accel.between(-4.0, 3.0))
    indexes = np.flatnonzero(valid.to_numpy())
    for group in np.split(indexes, np.flatnonzero(np.diff(indexes) > 1) + 1):
      if len(group) < 60:
        continue
      part = frame.iloc[group].iloc[::stride].copy()
      if len(part) >= 30 and part.time.diff().dropna().between(0.04, 0.20).mean() >= 0.95:
        sequences.append((route, part))
  return sequences


def command_residuals(values: np.ndarray, sequences: list[tuple[str, pd.DataFrame]]) -> np.ndarray:
  controller = ControllerParameters.from_array(values)
  residuals = []
  for _, frame in sequences:
    x = frame[["time", "v_ego", "plan_speed", "plan_accel", "accel_output"]].to_numpy(float)
    predicted = controller_command(x[:, 2] - x[:, 1], x[:, 3], x[:, 0], controller)
    residuals.append(predicted - x[:, 4])
  return np.concatenate(residuals)


def rollout_residuals(values: np.ndarray, sequences: list[tuple[str, pd.DataFrame]],
                      plant: PlantParameters, horizon_s: float) -> np.ndarray:
  """Closed-loop loss: simulated vehicle state must reproduce logged state.

  Each short chunk resets to the measured initial state.  This keeps errors
  local to the controller/plant mismatch instead of allowing a single grade or
  lead-vehicle modeling error to dominate a whole route.
  """
  controller = ControllerParameters.from_array(values)
  residuals = []
  for _, frame in sequences:
    x = frame[["time", "v_ego", "a_ego", "plan_speed", "plan_accel"]].to_numpy(float)
    dt = float(np.median(np.diff(x[:, 0])))
    horizon = max(10, round(horizon_s / dt))
    for begin in range(0, len(x) - horizon, horizon):
      part = x[begin:begin + horizon + 1]
      speed, accel, _ = simulate_reference_replay(part[:, 0], part[:, 3], part[:, 4], part[0, 1], part[0, 2], plant, controller)
      # Express speed error as acceleration over the training horizon so it
      # shares a useful scale with the acceleration residual.
      residuals.append(0.35 * (speed[1:] - part[1:, 1]) / horizon_s)
      residuals.append(0.65 * (accel[1:] - part[1:, 2]))
  return np.concatenate(residuals)


def reference_replay_metrics(sequences: list[tuple[str, pd.DataFrame]], plant: PlantParameters,
                             controller: ControllerParameters, horizon_s: float) -> dict[str, float]:
  simulated_error, actual_error, command_error = [], [], []
  by_route: dict[str, list[float]] = {}
  for route, frame in sequences:
    x = frame[["time", "v_ego", "a_ego", "plan_speed", "plan_accel", "accel_output"]].to_numpy(float)
    dt = float(np.median(np.diff(x[:, 0])))
    horizon = max(10, round(horizon_s / dt))
    for begin in range(0, len(x) - horizon, horizon):
      part = x[begin:begin + horizon + 1]
      speed, _, command = simulate_reference_replay(part[:, 0], part[:, 3], part[:, 4], part[0, 1], part[0, 2], plant, controller)
      sim = speed[1:] - part[1:, 3]
      actual = part[1:, 1] - part[1:, 3]
      simulated_error.extend(sim)
      actual_error.extend(actual)
      command_error.extend(command[1:] - part[1:, 5])
      by_route.setdefault(route, []).extend(sim)
  simulated_error, actual_error, command_error = map(np.asarray, (simulated_error, actual_error, command_error))
  return {
    "reference_replay_horizon_s": horizon_s,
    "windows": int(len(simulated_error)),
    "simulated_tracking_rmse_mph": float(np.sqrt(np.mean(simulated_error ** 2)) * 2.236936),
    "recorded_tracking_rmse_mph": float(np.sqrt(np.mean(actual_error ** 2)) * 2.236936),
    "simulated_tracking_p95_abs_mph": float(np.quantile(np.abs(simulated_error), 0.95) * 2.236936),
    "command_rmse_mps2": float(np.sqrt(np.mean(command_error ** 2))),
    "per_route_simulated_tracking_rmse_mph": {route: float(np.sqrt(np.mean(np.asarray(err) ** 2)) * 2.236936) for route, err in by_route.items()},
  }


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--split", default="training")
  parser.add_argument("--horizon-s", type=float, default=10.0)
  parser.add_argument("--train-horizon-s", type=float, default=5.0)
  parser.add_argument("--objective", choices=("rollout", "command"), default="rollout")
  parser.add_argument("--max-nfev", type=int, default=120)
  args = parser.parse_args()
  routes = routes_for_split(args.split)
  if not routes:
    raise SystemExit(f"No routes assigned to split '{args.split}'")
  sequences = load_controller_sequences(routes)
  if not sequences:
    raise SystemExit("No usable longitudinal plan/controller sequences found")
  plant_data = json.loads((ARTIFACTS / "plant_model.json").read_text(encoding="utf-8"))
  plant = PlantParameters(**plant_data["parameters"])
  print(f"Closed-loop controller fit: {len(sequences)} sequences / {sum(len(f) for _, f in sequences):,} samples", flush=True)
  if args.objective == "rollout":
    residual_fn = rollout_residuals
    residual_args = (sequences, plant, args.train_horizon_s)
  else:
    residual_fn = command_residuals
    residual_args = (sequences,)
  result = least_squares(residual_fn, CONTROLLER_INITIAL.to_array(), args=residual_args,
                         bounds=(CONTROLLER_LOWER, CONTROLLER_UPPER), loss="soft_l1", f_scale=0.18,
                         max_nfev=args.max_nfev, verbose=1)
  controller = ControllerParameters.from_array(result.x)
  command_residual = command_residuals(result.x, sequences)
  training_residual = residual_fn(result.x, *residual_args)
  report = {
    "split": args.split,
    "routes": routes,
    "sequence_count": len(sequences),
    "sample_count": sum(len(f) for _, f in sequences),
    "objective": args.objective,
    "training_horizon_s": args.train_horizon_s if args.objective == "rollout" else None,
    "optimizer": {"success": bool(result.success), "message": result.message, "nfev": result.nfev, "cost": float(result.cost)},
    "plant_parameters": asdict(plant),
    "controller_parameters": asdict(controller),
    "objective_rmse": float(np.sqrt(np.mean(training_residual ** 2))),
    "command_fit_rmse_mps2": float(np.sqrt(np.mean(command_residual ** 2))),
    **reference_replay_metrics(sequences, plant, controller, args.horizon_s),
  }
  ARTIFACTS.mkdir(exist_ok=True)
  (ARTIFACTS / "closed_loop_model.json").write_text(json.dumps({"parameter_names": CONTROLLER_PARAMETER_NAMES, "parameters": asdict(controller)}, indent=2), encoding="utf-8")
  (ARTIFACTS / "closed_loop_training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
