#!/usr/bin/env python3
"""Extract longitudinal-control signals from local sunnypilot rlogs."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from openpilot.tools.lib.logreader import LogReader


DEFAULT_LOG_ROOT = Path("/home/caleb/openpilot/route-data")
DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent / "cache"


def segment_number(path: Path) -> int:
  return int(path.parent.name.rsplit("--", 1)[1])


def route_files(log_root: Path, route: str) -> list[Path]:
  files = list(log_root.glob(f"{route}--*/rlog.zst"))
  return sorted(files, key=segment_number)


def enum_name(value) -> str:
  return str(value).split(".")[-1]


def extract_route(log_root: Path, route: str) -> tuple[pd.DataFrame, dict[str, str]]:
  files = route_files(log_root, route)
  if not files:
    raise FileNotFoundError(f"No rlogs found for {route} under {log_root}")

  rows: dict[str, list[dict]] = defaultdict(list)
  metadata: dict[str, str] = {"route": route, "segments": str(len(files))}
  # The device clock can be stale at ignition, but the final segment mtime is
  # synchronized. Back-calculate the route start from the segment number.
  last_segment = segment_number(files[-1])
  end_wall = max(path.stat().st_mtime for path in files)
  start_wall = end_wall - last_segment * 60
  metadata.update({
    "route_start_local": datetime.fromtimestamp(start_wall, ZoneInfo("America/Los_Angeles")).isoformat(),
    "route_end_local": datetime.fromtimestamp(end_wall, ZoneInfo("America/Los_Angeles")).isoformat(),
  })

  for path in files:
    for msg in LogReader(str(path), sort_by_time=True, only_union_types=True):
      service = msg.which()
      t = msg.logMonoTime / 1e9

      if service == "carState":
        x = msg.carState
        rows[service].append({
          "t": t,
          "v_ego": float(x.vEgo),
          "a_ego": float(x.aEgo),
          "v_cruise": float(x.vCruise) / 3.6,
          "standstill": bool(x.standstill),
          "gas_pressed": bool(x.gasPressed),
          "brake_pressed": bool(x.brakePressed),
        })
      elif service == "carControl":
        x = msg.carControl
        rows[service].append({
          "t": t,
          "enabled": bool(x.enabled),
          "long_active": bool(x.longActive),
          "accel_request": float(x.actuators.accel),
          "long_state": enum_name(x.actuators.longControlState),
          "set_speed": float(x.hudControl.setSpeed),
          "lead_distance_bars": int(x.hudControl.leadDistanceBars),
        })
      elif service == "carOutput":
        x = msg.carOutput.actuatorsOutput
        rows[service].append({
          "t": t,
          "accel_output": float(x.accel),
          "gas_output": float(x.gas),
          "brake_output": float(x.brake),
        })
      elif service == "controlsState":
        x = msg.controlsState
        rows[service].append({
          "t": t,
          "accel_p": float(x.upAccelCmd),
          "accel_i": float(x.uiAccelCmd),
          "accel_f": float(x.ufAccelCmd),
          "force_decel": bool(x.forceDecel),
        })
      elif service == "longitudinalPlan":
        x = msg.longitudinalPlan
        rows[service].append({
          "t": t,
          "plan_speed": float(x.speeds[0]) if len(x.speeds) else np.nan,
          "plan_accel": float(x.accels[0]) if len(x.accels) else np.nan,
          "a_target": float(x.aTarget),
          "has_lead": bool(x.hasLead),
          "plan_source": enum_name(x.longitudinalPlanSource),
          "should_stop": bool(x.shouldStop),
          "allow_throttle": bool(x.allowThrottle),
          "allow_brake": bool(x.allowBrake),
        })
      elif service == "radarState":
        x = msg.radarState.leadOne
        rows[service].append({
          "t": t,
          "lead_status": bool(x.status),
          "d_rel": float(x.dRel),
          "v_rel": float(x.vRel),
          "v_lead": float(x.vLead),
          "a_lead": float(x.aLeadK),
          "lead_prob": float(x.modelProb),
        })
      elif service == "gpsLocationExternal":
        x = msg.gpsLocationExternal
        rows[service].append({
          "t": t,
          "gps_lat": float(x.latitude),
          "gps_lon": float(x.longitude),
          "gps_altitude": float(x.altitude),
          "gps_speed": float(x.speed),
          "gps_bearing": float(x.bearingDeg),
          "gps_accuracy": float(x.horizontalAccuracy),
          "gps_time_unix_ms": int(x.unixTimestampMillis),
          "gps_has_fix": bool(x.hasFix),
          "gps_satellites": int(x.satelliteCount),
        })
      elif service == "selfdriveState":
        x = msg.selfdriveState
        rows[service].append({
          "t": t,
          "personality": enum_name(x.personality),
          "selfdrive_enabled": bool(x.enabled),
        })
      elif service == "carParams" and "car_fingerprint" not in metadata:
        x = msg.carParams
        metadata.update({
          "car_fingerprint": str(x.carFingerprint),
          "longitudinal_actuator_delay": str(float(x.longitudinalActuatorDelay)),
        })
      elif service == "initData" and "git_commit" not in metadata:
        x = msg.initData
        metadata.update({
          "git_commit": str(x.gitCommit),
          "git_branch": str(x.gitBranch),
          "software_version": str(x.version),
        })

  if not rows["carState"]:
    raise RuntimeError(f"No carState messages found in {route}")

  gps = pd.DataFrame(rows["gpsLocationExternal"])
  if not gps.empty:
    gps = gps[(gps["gps_has_fix"]) & gps["gps_lat"].between(-90, 90) & gps["gps_lon"].between(-180, 180)]
    if not gps.empty:
      metadata["gps_start_local"] = datetime.fromtimestamp(
        gps["gps_time_unix_ms"].min() / 1000, ZoneInfo("America/Los_Angeles")).isoformat()
      metadata["gps_end_local"] = datetime.fromtimestamp(
        gps["gps_time_unix_ms"].max() / 1000, ZoneInfo("America/Los_Angeles")).isoformat()
      # Align GPS UTC to the log's monotonic clock. The first valid fix can be
      # minutes after ignition, so it must not be treated as route time zero.
      gps_offset = (gps["gps_time_unix_ms"] / 1000 - gps["t"]).median()
      car_times = [row["t"] for row in rows["carState"]]
      route_start_epoch = gps_offset + min(car_times)
      route_end_epoch = gps_offset + max(car_times)
      metadata["route_start_local"] = datetime.fromtimestamp(route_start_epoch, ZoneInfo("America/Los_Angeles")).isoformat()
      metadata["route_end_local"] = datetime.fromtimestamp(route_end_epoch, ZoneInfo("America/Los_Angeles")).isoformat()
      metadata["gps_points"] = str(len(gps))

  # A 20 Hz timeline preserves longitudinal dynamics while keeping Plotly responsive.
  base = pd.DataFrame(rows["carState"]).sort_values("t").iloc[::5].reset_index(drop=True)
  for service in ("carControl", "carOutput", "controlsState", "longitudinalPlan", "radarState", "selfdriveState", "gpsLocationExternal"):
    other = pd.DataFrame(rows[service]).sort_values("t")
    if not other.empty:
      base = pd.merge_asof(base, other, on="t", direction="nearest", tolerance=0.15)

  base["time"] = base["t"] - base["t"].iloc[0]
  base["segment"] = np.floor(base["time"] / 60).astype(int)
  base["speed_mph"] = base["v_ego"] * 2.236936
  base["set_speed_mph"] = base["set_speed"] * 2.236936
  base["plan_speed_mph"] = base["plan_speed"] * 2.236936
  base["speed_error_mph"] = (base["v_ego"] - base["set_speed"]) * 2.236936
  base["plan_error_mph"] = (base["v_ego"] - base["plan_speed"]) * 2.236936
  base["time_gap"] = np.where((base["lead_status"] == True) & (base["v_ego"] > 0.5),  # noqa: E712
                                    base["d_rel"] / base["v_ego"], np.nan)
  t_follow = base["personality"].map({"relaxed": 1.75, "standard": 1.45, "aggressive": 1.25}).fillna(1.45)
  # Same steady-state following-distance model used by long_mpc.py.
  base["desired_distance"] = (
    (base["v_ego"] ** 2 - base["v_lead"].clip(lower=0) ** 2) / (2 * 2.5)
    + t_follow * base["v_ego"] + 6.0
  ).clip(lower=6.0)
  base["distance_error"] = base["d_rel"] - base["desired_distance"]

  # These drives predate the CR-V hysteresis patch. This exactly reconstructs
  # the old Bosch crossover used to build ACC_CONTROL.
  base["brake_request"] = base["long_active"].fillna(False) & (base["accel_output"] < -0.2)
  base["gas_request"] = base["long_active"].fillna(False) & ~base["brake_request"] & (base["accel_output"] > -0.2)
  base["can_gas_command"] = np.where(base["gas_request"], base["gas_output"], -30000.0)
  base["command_mode"] = np.select(
    [base["brake_request"], base["gas_request"]], ["brake", "gas"], default="inactive")
  dt = base["time"].diff().clip(lower=0.01)
  base["actual_jerk"] = base["a_ego"].diff() / dt
  base["command_jerk"] = base["accel_output"].diff() / dt

  return base, metadata


def discover_routes(log_root: Path) -> list[str]:
  return sorted({p.parent.name.rsplit("--", 1)[0] for p in log_root.glob("*--*/rlog.zst")})


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("routes", nargs="*", help="Route prefixes; defaults to all local routes")
  parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
  parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
  args = parser.parse_args()

  routes = args.routes or discover_routes(args.log_root)
  args.cache_root.mkdir(parents=True, exist_ok=True)
  for route in routes:
    print(f"Extracting {route} ...", flush=True)
    frame, metadata = extract_route(args.log_root, route)
    frame.to_parquet(args.cache_root / f"{route}.parquet", index=False, compression="zstd")
    pd.Series(metadata).to_json(args.cache_root / f"{route}.json", indent=2)
    print(f"  {len(frame):,} samples, {frame['time'].iloc[-1] / 60:.1f} minutes", flush=True)


if __name__ == "__main__":
  main()
