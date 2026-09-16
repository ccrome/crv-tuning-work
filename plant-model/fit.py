#!/usr/bin/env python3
"""Fit and evaluate the initial CR-V grey-box longitudinal plant model."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from plant import INITIAL_PARAMETERS, LOWER_BOUNDS, PARAMETER_NAMES, UPPER_BOUNDS, PlantParameters, predict_one_step, rollout


ROOT = Path(__file__).resolve().parent
CACHE = ROOT.parent / "log-dashboard" / "cache"
SPLITS = ROOT.parent / "route-data-splits" / "index.csv"
ARTIFACTS = ROOT / "artifacts"


def routes_for_split(split: str) -> list[str]:
  with open(SPLITS, newline="", encoding="utf-8") as f:
    return [row["route"] for row in csv.DictReader(f) if row["split"] == split]


def load_sequences(routes: list[str], stride: int = 2) -> list[tuple[str, pd.DataFrame]]:
  sequences: list[tuple[str, pd.DataFrame]] = []
  required = ["time", "v_ego", "a_ego", "accel_output", "long_active", "gas_pressed", "brake_pressed"]
  for route in routes:
    frame = pd.read_parquet(CACHE / f"{route}.parquet", columns=required).dropna()
    valid = (
      frame["long_active"].astype(bool)
      & ~frame["gas_pressed"].astype(bool)
      & ~frame["brake_pressed"].astype(bool)
      & (frame["v_ego"] >= 1.5)
      & frame["accel_output"].between(-3.5, 2.5)
    )
    indices = np.flatnonzero(valid.to_numpy())
    for group in np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1):
      if len(group) < 40:
        continue
      part = frame.iloc[group].iloc[::stride].copy()
      dt = part["time"].diff().dropna()
      if len(dt) and dt.between(0.04, 0.20).mean() < 0.95:
        continue
      if len(part) >= 20:
        sequences.append((route, part))
  return sequences


def one_step_residuals(values: np.ndarray, sequences: list[tuple[str, pd.DataFrame]]) -> np.ndarray:
  parameters = PlantParameters.from_array(values)
  residuals = []
  for _, frame in sequences:
    values_np = frame[["time", "v_ego", "a_ego", "accel_output"]].to_numpy(dtype=float)
    predicted_v, predicted_a, _ = predict_one_step(*values_np.T, parameters)
    actual_v = values_np[1:, 1]
    actual_a = values_np[1:, 2]
    # Acceleration drives the fit; speed residual is expressed as an equivalent
    # acceleration so its scale is comparable at the 10 Hz training rate.
    dt = np.diff(values_np[:, 0])
    residuals.append(predicted_a - actual_a)
    residuals.append(0.35 * (predicted_v - actual_v) / dt)
  return np.concatenate(residuals)


def rollout_metrics(sequences: list[tuple[str, pd.DataFrame]], parameters: PlantParameters,
                    horizon_s: float = 5.0) -> dict[str, float]:
  speed_errors, accel_errors = [], []
  for _, frame in sequences:
    x = frame[["time", "v_ego", "a_ego", "accel_output"]].to_numpy(dtype=float)
    dt = float(np.median(np.diff(x[:, 0])))
    horizon = max(2, round(horizon_s / dt))
    for begin in range(0, len(x) - horizon, horizon):
      part = x[begin:begin + horizon + 1]
      pred_v, pred_a = rollout(part[:, 0], part[0, 1], part[0, 2], part[:, 3], parameters)
      speed_errors.extend(pred_v[1:] - part[1:, 1])
      accel_errors.extend(pred_a[1:] - part[1:, 2])
  speed_errors = np.asarray(speed_errors)
  accel_errors = np.asarray(accel_errors)
  return {
    "rollout_horizon_s": horizon_s,
    "rollout_speed_rmse_mps": float(np.sqrt(np.mean(speed_errors ** 2))),
    "rollout_speed_rmse_mph": float(np.sqrt(np.mean(speed_errors ** 2)) * 2.236936),
    "rollout_accel_rmse_mps2": float(np.sqrt(np.mean(accel_errors ** 2))),
    "rollout_speed_p95_abs_mph": float(np.quantile(np.abs(speed_errors), 0.95) * 2.236936),
  }


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--split", default="training")
  parser.add_argument("--max-nfev", type=int, default=120)
  args = parser.parse_args()

  routes = routes_for_split(args.split)
  if not routes:
    raise SystemExit(f"No routes assigned to split '{args.split}' in {SPLITS}")
  sequences = load_sequences(routes)
  if not sequences:
    raise SystemExit("No usable moving, longitudinal-active sequences found")

  sample_count = sum(len(frame) for _, frame in sequences)
  print(f"Fitting {len(sequences)} contiguous sequences / {sample_count:,} samples from {routes}", flush=True)
  result = least_squares(
    one_step_residuals, INITIAL_PARAMETERS.to_array(), args=(sequences,),
    bounds=(LOWER_BOUNDS, UPPER_BOUNDS), loss="soft_l1", f_scale=0.18,
    max_nfev=args.max_nfev, verbose=1,
  )
  parameters = PlantParameters.from_array(result.x)
  residual = one_step_residuals(result.x, sequences)
  report = {
    "split": args.split,
    "routes": routes,
    "sequence_count": len(sequences),
    "sample_count": sample_count,
    "optimizer": {"success": bool(result.success), "message": result.message, "nfev": result.nfev, "cost": float(result.cost)},
    "parameters": asdict(parameters),
    "one_step_residual_rmse_mps2": float(np.sqrt(np.mean(residual ** 2))),
    **rollout_metrics(sequences, parameters),
  }
  ARTIFACTS.mkdir(exist_ok=True)
  with open(ARTIFACTS / "plant_model.json", "w", encoding="utf-8") as f:
    json.dump({"parameter_names": PARAMETER_NAMES, "parameters": asdict(parameters)}, f, indent=2)
  with open(ARTIFACTS / "training_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
