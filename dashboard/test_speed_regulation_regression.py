"""Log-backed CR-V speed-regulation regressions.

These tests intentionally fail on the recorded stock baseline. When evaluating
a speed-regulation change, replace the route IDs with matched candidate routes
and remove ``expectedFailure`` to make the limits required passes.
"""

import unittest
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).with_name("cache")
WINDOW_SECONDS = 30
MAX_PEAK_TO_PEAK_MPH = 1.0
MAX_OVERSHOOT_MPH = 0.5


def stable_cruise_windows(route: str, lower_set_speed_mph: float, upper_set_speed_mph: float) -> list[dict]:
  """Return strict no-lead, fixed-set-speed 30-second windows from one route."""
  frame = pd.read_parquet(CACHE / f"{route}.parquet").sort_values("time").copy()
  frame["second"] = frame["time"].astype(int)
  seconds = frame.groupby("second").agg(
    speed_mph=("speed_mph", "mean"),
    set_speed_mph=("set_speed_mph", "mean"),
    long_active=("long_active", "mean"),
    lead_status=("lead_status", "mean"),
    cruise_source=("plan_source", lambda source: (source == "cruise").mean()),
    gas_pressed=("gas_pressed", "mean"),
    brake_pressed=("brake_pressed", "mean"),
  )

  windows = []
  for end in range(WINDOW_SECONDS - 1, len(seconds)):
    window = seconds.iloc[end - WINDOW_SECONDS + 1:end + 1]
    error_mph = window["speed_mph"] - window["set_speed_mph"]
    set_speed_mph = window["set_speed_mph"].mean()
    valid = (
      window["long_active"].min() > 0.99
      and window["lead_status"].max() == 0.0
      and window["cruise_source"].min() > 0.99
      and window["gas_pressed"].max() == 0.0
      and window["brake_pressed"].max() == 0.0
      and window["set_speed_mph"].max() - window["set_speed_mph"].min() < 0.1
      and error_mph.abs().max() <= 2.0
      and lower_set_speed_mph <= set_speed_mph < upper_set_speed_mph
    )
    if valid:
      windows.append({
        "start_s": int(window.index[0]),
        "set_speed_mph": float(set_speed_mph),
        "peak_to_peak_mph": float(error_mph.max() - error_mph.min()),
        "overshoot_mph": float(error_mph.max()),
      })
  return windows


class TestCrvSpeedRegulationRegression(unittest.TestCase):
  def assert_regulation_limits(self, routes: tuple[str, ...], lower_set_speed_mph: float, upper_set_speed_mph: float):
    windows = [
      window
      for route in routes
      for window in stable_cruise_windows(route, lower_set_speed_mph, upper_set_speed_mph)
    ]
    self.assertTrue(windows, "no qualifying steady no-lead cruise windows")
    worst_peak_to_peak = max(windows, key=lambda window: window["peak_to_peak_mph"])
    worst_overshoot = max(windows, key=lambda window: window["overshoot_mph"])
    self.assertLessEqual(worst_peak_to_peak["peak_to_peak_mph"], MAX_PEAK_TO_PEAK_MPH, worst_peak_to_peak)
    self.assertLessEqual(worst_overshoot["overshoot_mph"], MAX_OVERSHOOT_MPH, worst_overshoot)

  @unittest.expectedFailure
  def test_highway_speed_regulation(self):
    """Stock highway cruise has excessive steady-state speed variation."""
    self.assert_regulation_limits(("0000005c--3c70bb383d", "0000005d--46b3832579"), 55.0, 100.0)

  @unittest.expectedFailure
  def test_moderate_speed_regulation(self):
    """The same regulation issue is measurable at moderate set speeds."""
    self.assert_regulation_limits(("00000004--0a2432880c", "00000005--e710b97a54"), 25.0, 55.0)
