"""Log-backed regression for the driver-marked high-speed route-1e approach."""

import unittest
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).with_name("cache")
ROUTE = "0000001e--2d841e7d0b"


class TestHighSpeedBrakingRegression(unittest.TestCase):
  @unittest.expectedFailure
  def test_driver_marked_closing_lead_reaches_strong_braking_before_takeover(self):
    """Require enough outgoing braking before the 72 mph closing-lead takeover.

    In the 1974--1975 s pre-brake window, the lead is about 35--45 m away and
    closing at roughly 4.3 m/s. The driver brakes before the controller reaches
    the `-1.2 m/s²` outgoing-braking threshold.
    """
    frame = pd.read_parquet(CACHE / f"{ROUTE}.parquet")
    pre_takeover = frame[frame["time"].between(1974.0, 1974.787, inclusive="left")]
    credible_closing_lead = pre_takeover[
      (pre_takeover["long_active"].fillna(False))
      & (pre_takeover["lead_status"].fillna(False))
      & (pre_takeover["d_rel"].between(30.0, 50.0))
      & (pre_takeover["v_rel"] < -4.0)
      & ~pre_takeover["brake_pressed"].fillna(False)
    ]
    self.assertFalse(credible_closing_lead.empty, "missing the documented pre-takeover window")
    self.assertLessEqual(credible_closing_lead["accel_output"].min(), -1.2)
