#!/usr/bin/env python3
"""Streamlit dashboard for sunnypilot longitudinal-control logs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import find_peaks
import streamlit as st


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"


st.set_page_config(page_title="CR-V longitudinal tuning", page_icon="🚗", layout="wide")


@st.cache_data(show_spinner=False)
def load_route(route: str) -> tuple[pd.DataFrame, dict]:
  frame = pd.read_parquet(CACHE / f"{route}.parquet")
  with open(CACHE / f"{route}.json", encoding="utf-8") as f:
    metadata = json.load(f)
  return frame, metadata


def contiguous_windows(frame: pd.DataFrame, mask: pd.Series, min_duration: float, join_gap: float = 2.0) -> list[tuple[float, float]]:
  times = frame.loc[mask.fillna(False), "time"].to_numpy()
  if not len(times):
    return []
  cuts = np.flatnonzero(np.diff(times) > join_gap) + 1
  groups = np.split(times, cuts)
  return [(float(g[0]), float(g[-1])) for g in groups if g[-1] - g[0] >= min_duration]


def route_events(frame: pd.DataFrame, kind: str) -> list[tuple[float, float]]:
  if kind == "Stop-and-go":
    mask = frame["long_active"].fillna(False) & frame["lead_status"].fillna(False) & (frame["v_ego"] < 8.0)
    return contiguous_windows(frame, mask, 8.0, 3.0)
  if kind == "Highway":
    mask = frame["long_active"].fillna(False) & (frame["v_ego"] > 20.0)
    return contiguous_windows(frame, mask, 20.0, 3.0)
  return [(float(frame["time"].iloc[0]), float(frame["time"].iloc[-1]))]


def mode_switches(frame: pd.DataFrame) -> int:
  mode = frame.loc[frame["command_mode"].isin(["gas", "brake"]), "command_mode"]
  return int((mode != mode.shift()).sum() - (1 if len(mode) else 0))


def oscillation_metrics(frame: pd.DataFrame) -> tuple[float, float, int]:
  cruise = frame[
    frame["long_active"].fillna(False)
    & (frame["v_ego"] > 20)
    & (frame["plan_source"] == "cruise")
    & (frame["set_speed"] > 1)
    & (frame["speed_error_mph"].abs() < 6)
  ].copy()
  if len(cruise) < 100:
    return np.nan, np.nan, 0
  error = cruise["speed_error_mph"].rolling(20, center=True, min_periods=1).mean().to_numpy()
  peaks, _ = find_peaks(error, prominence=0.15, distance=40)
  troughs, _ = find_peaks(-error, prominence=0.15, distance=40)
  return float(np.nanmax(error)), float(np.nanstd(error)), int(len(peaks) + len(troughs))


def line(fig, row: int, x, y, name: str, color: str, *, dash: str | None = None, secondary_y: bool = False) -> None:
  fig.add_trace(go.Scattergl(
    x=x, y=y, name=name, mode="lines",
    line={"color": color, "width": 1.5, **({"dash": dash} if dash else {})},
    hovertemplate=f"%{{x:.2f}} s<br>{name}: %{{y:.3f}}<extra></extra>",
  ), row=row, col=1, secondary_y=secondary_y)


def main_figure(frame: pd.DataFrame, route_start: datetime | None = None,
                regions: dict[str, list[tuple[float, float]]] | None = None) -> go.Figure:
  colors = {
    "blue": "#3b82f6", "orange": "#f59e0b", "green": "#10b981", "red": "#ef4444",
    "purple": "#8b5cf6", "cyan": "#06b6d4", "pink": "#ec4899", "gray": "#94a3b8",
  }
  fig = make_subplots(
    rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.025,
    row_heights=[0.22, 0.24, 0.18, 0.17, 0.19],
    specs=[[{}], [{}], [{}], [{"secondary_y": True}], [{"secondary_y": True}]],
    subplot_titles=(
      "Speed — actual, plan, and cruise setpoint",
      "Acceleration — planner input, controller request/output, and vehicle response",
      "Longitudinal controller terms",
      "Honda Bosch gas/brake crossover",
      "Lead tracking and following distance",
    ),
  )
  # Shade the behavior regions across every subplot so signal changes can be
  # compared directly against the detected driving context.
  if regions:
    region_styles = {
      "Stop-and-go": {"color": "#f59e0b", "label": "stop-and-go"},
      "Highway": {"color": "#3b82f6", "label": "highway"},
    }
    visible_start = float(frame["time"].iloc[0]) if len(frame) else 0.0
    visible_end = float(frame["time"].iloc[-1]) if len(frame) else 0.0
    for kind, windows in regions.items():
      style = region_styles[kind]
      for start, end in windows:
        x0, x1 = max(start, visible_start), min(end, visible_end)
        if x1 <= x0:
          continue
        for row in range(1, 6):
          xref = "x" if row == 1 else f"x{row}"
          yref = "y domain" if row == 1 else f"y{row} domain"
          fig.add_shape(
            type="rect", xref=xref, yref=yref, x0=x0, x1=x1, y0=0, y1=1,
            fillcolor=style["color"], opacity=0.10,
            line_width=1, line_color=style["color"], layer="below",
          )
        fig.add_annotation(
          x=x0, y=1, xref="x", yref="y domain", text=style["label"],
          showarrow=False, xanchor="left", yanchor="bottom",
          font={"size": 10, "color": style["color"]},
        )
    # Shape legends are not supported by Plotly, so provide legend-only keys.
    for kind, style in region_styles.items():
      if regions.get(kind):
        fig.add_trace(go.Scatter(
          x=[None], y=[None], mode="markers", name=f"{kind} region",
          marker={"size": 10, "color": style["color"], "symbol": "square", "opacity": 0.35},
          hoverinfo="skip", showlegend=True,
        ), row=1, col=1)
  x = frame["time"]
  line(fig, 1, x, frame["speed_mph"], "Controller speed (vEgo)", colors["blue"])
  if "speed_cluster_mph" in frame and frame["speed_cluster_mph"].notna().any() and (frame["speed_cluster_mph"] > 0).any():
    line(fig, 1, x, frame["speed_cluster_mph"], "Honda cluster speed", colors["cyan"], dash="dash")
  if {"gps_speed_mph", "gps_has_fix", "gps_accuracy"}.issubset(frame.columns):
    gps_speed = frame["gps_speed_mph"].where(frame["gps_has_fix"].fillna(False) & frame["gps_accuracy"].between(0, 25))
    line(fig, 1, x, gps_speed, "GPS ground speed", colors["orange"], dash="dot")
  line(fig, 1, x, frame["plan_speed_mph"], "Plan speed", colors["green"])
  line(fig, 1, x, frame["set_speed_mph"], "Cruise setpoint", colors["pink"], dash="dot")

  line(fig, 2, x, frame["a_ego"], "Actual accel", colors["blue"])
  line(fig, 2, x, frame["plan_accel"], "Planner accel", colors["green"])
  line(fig, 2, x, frame["accel_request"], "Controller request", colors["purple"])
  line(fig, 2, x, frame["accel_output"], "Honda output", colors["orange"], dash="dash")

  line(fig, 3, x, frame["accel_p"], "P term", colors["red"])
  line(fig, 3, x, frame["accel_i"], "I term", colors["blue"])
  line(fig, 3, x, frame["accel_f"], "Feedforward", colors["green"])

  line(fig, 4, x, frame["accel_output"], "Accel command", colors["purple"])
  line(fig, 4, x, frame["gas_output"], "Gas command", colors["orange"], secondary_y=True)
  brake = frame["brake_request"].astype(float)
  fig.add_trace(go.Scattergl(
    x=x, y=brake, name="Brake request", mode="lines", fill="tozeroy",
    line={"color": colors["red"], "width": 1}, opacity=0.35,
    hovertemplate="%{x:.2f} s<br>Brake request: %{y:.0f}<extra></extra>",
  ), row=4, col=1, secondary_y=True)
  fig.add_hline(y=-0.2, line_dash="dot", line_color=colors["gray"], row=4, col=1,
                annotation_text="stock crossover −0.20 m/s²", annotation_position="bottom right")

  line(fig, 5, x, frame["d_rel"], "Measured lead distance", colors["blue"])
  line(fig, 5, x, frame["desired_distance"], "MPC desired distance", colors["green"], dash="dash")
  line(fig, 5, x, frame["v_rel"], "Lead relative speed", colors["orange"], secondary_y=True)

  if route_start is not None and len(frame):
    time_of_day = np.array([
      (route_start + timedelta(seconds=float(t))).strftime("%H:%M:%S")
      for t in frame["time"]
    ])
    for trace in fig.data:
      if trace.x is not None and len(trace.x) == len(frame) and trace.hovertemplate:
        trace.customdata = time_of_day
        trace.hovertemplate = "%{customdata}<br>" + trace.hovertemplate

  fig.update_yaxes(title_text="mph", row=1, col=1)
  fig.update_yaxes(title_text="m/s²", row=2, col=1)
  fig.update_yaxes(title_text="m/s²", row=3, col=1)
  fig.update_yaxes(title_text="m/s²", row=4, col=1, secondary_y=False)
  fig.update_yaxes(title_text="gas / brake", row=4, col=1, secondary_y=True)
  fig.update_yaxes(title_text="distance (m)", row=5, col=1, secondary_y=False)
  fig.update_yaxes(title_text="vRel (m/s)", row=5, col=1, secondary_y=True)
  fig.update_xaxes(title_text="route time (seconds)", row=5, col=1)
  if route_start is not None and len(frame):
    tickvals = np.linspace(float(frame["time"].iloc[0]), float(frame["time"].iloc[-1]), 8)
    ticktext = [(route_start + timedelta(seconds=float(t))).strftime("%H:%M:%S") for t in tickvals]
    fig.update_layout(xaxis6={
      "overlaying": "x5", "anchor": "free", "position": 1.0, "side": "top",
      "matches": "x5", "domain": [0, 1], "showline": True, "showticklabels": True,
      "ticks": "outside", "showgrid": False, "title": {"text": "time of day"},
      "tickvals": tickvals, "ticktext": ticktext,
    })
  fig.update_layout(
    height=1200, hovermode="x unified", template="plotly_dark",
    margin={"l": 60, "r": 190, "t": 100, "b": 45},
    legend={"orientation": "v", "yanchor": "top", "y": 1, "xanchor": "left", "x": 1.02},
    uirevision="longitudinal-dashboard",
  )
  return fig


def gps_figure(frame: pd.DataFrame, regions: dict[str, list[tuple[float, float]]] | None = None) -> go.Figure | None:
  if not {"gps_lat", "gps_lon"}.issubset(frame.columns):
    return None
  gps = frame.dropna(subset=["gps_lat", "gps_lon"]).copy()
  gps = gps[gps["gps_lat"].between(-90, 90) & gps["gps_lon"].between(-180, 180)]
  gps = gps[(gps["gps_lat"].abs() > 0.0001) | (gps["gps_lon"].abs() > 0.0001)]
  # gpsLocationExternal retains coordinates while the receiver is acquiring a
  # fix. Keep only quality fixes, then reject jumps that would require an
  # impossible road speed (the observed car never approaches this threshold).
  if "gps_has_fix" in gps:
    gps = gps[gps["gps_has_fix"].fillna(False)]
  if "gps_accuracy" in gps:
    gps = gps[gps["gps_accuracy"].between(0, 100)]
  if "gps_satellites" in gps:
    gps = gps[gps["gps_satellites"] >= 4]
  if len(gps) > 1:
    lat1, lon1 = np.radians(gps["gps_lat"].to_numpy()[:-1]), np.radians(gps["gps_lon"].to_numpy()[:-1])
    lat2, lon2 = np.radians(gps["gps_lat"].to_numpy()[1:]), np.radians(gps["gps_lon"].to_numpy()[1:])
    earth_radius_m = 6_371_000.0
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    jump_m = 2 * earth_radius_m * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    dt = np.maximum(np.diff(gps["time"].to_numpy()), 0.01)
    keep = np.r_[True, (jump_m / dt) < 80.0]
    gps = gps.loc[keep]
  if len(gps) < 2:
    return None
  gps["event_label"] = "unclassified"
  gps["time_of_day"] = pd.to_datetime(
    gps["gps_time_unix_ms"], unit="ms", utc=True
  ).dt.tz_convert("America/Los_Angeles").dt.strftime("%H:%M:%S")
  for kind, windows in (regions or {}).items():
    for window_idx, (start_s, end_s) in enumerate(windows):
      gps.loc[gps["time"].between(start_s, end_s), "event_label"] = f"{kind} event {window_idx + 1}"
  gps = gps.iloc[::max(1, len(gps) // 5000)]
  start = gps.iloc[0]
  end = gps.iloc[-1]
  fig = go.Figure(go.Scattermapbox(
    lat=gps["gps_lat"], lon=gps["gps_lon"], mode="lines+markers",
    line={"width": 6, "color": "#111827"}, marker={"size": 3, "color": "#111827"},
    name="GPS track",
    customdata=gps[["time", "speed_mph", "time_of_day", "event_label"]],
    hovertemplate="%{customdata[0]:.1f} s<br>%{customdata[2]}<br>%{customdata[1]:.1f} mph<br>%{customdata[3]}<extra></extra>",
  ))
  region_colors = {"Stop-and-go": "#00e5ff", "Highway": "#2563eb"}
  for kind, color in region_colors.items():
    for window_idx, (start_s, end_s) in enumerate((regions or {}).get(kind, [])):
      points = gps[gps["time"].between(start_s, end_s)]
      if points.empty:
        continue
      fig.add_trace(go.Scattermapbox(
        lat=points["gps_lat"], lon=points["gps_lon"], mode="lines+markers",
        line={"width": 5, "color": color}, marker={"size": 8, "color": color},
        name=f"{kind} GPS points", legendgroup=kind, showlegend=window_idx == 0,
        customdata=points[["time", "speed_mph", "time_of_day"]],
        hovertemplate="%{customdata[0]:.1f} s<br>%{customdata[2]}<br>%{customdata[1]:.1f} mph<br>" + f"{kind} event {window_idx + 1}" + "<extra></extra>",
      ))
  fig.add_trace(go.Scattermapbox(
    lat=[start["gps_lat"], end["gps_lat"]], lon=[start["gps_lon"], end["gps_lon"]],
    mode="markers+text", text=["Start", "End"], textposition="top right",
    marker={"size": 10, "color": ["#10b981", "#ef4444"]}, name="Route endpoints",
    hovertemplate=["Start: %{lat:.6f}, %{lon:.6f}<extra></extra>", "End: %{lat:.6f}, %{lon:.6f}<extra></extra>"],
  ))
  fig.update_layout(
    mapbox={
      "style": "open-street-map",
      "center": {"lat": (gps["gps_lat"].min() + gps["gps_lat"].max()) / 2, "lon": (gps["gps_lon"].min() + gps["gps_lon"].max()) / 2},
      "zoom": 12,
    },
    height=560, margin={"l": 0, "r": 0, "t": 35, "b": 0},
    title="GPS route track (OpenStreetMap)", template="plotly_dark",
    showlegend=True,
  )
  return fig


def event_table(frame: pd.DataFrame, windows: list[tuple[float, float]], kind: str) -> pd.DataFrame:
  result = []
  for idx, (start, end) in enumerate(windows, 1):
    part = frame[frame["time"].between(start, end)]
    low = part[(part["v_ego"] < 2.0) & part["lead_status"].fillna(False)]
    result.append({
      "event": f"{kind} {idx}",
      "start_s": start,
      "end_s": end,
      "duration_s": end - start,
      "gas_brake_switches": mode_switches(part),
      "min_lead_distance_m": low["d_rel"].min() if len(low) else np.nan,
      "min_time_gap_s": part["time_gap"].min(),
      "max_actual_accel": part["a_ego"].max(),
      "min_actual_accel": part["a_ego"].min(),
    })
  return pd.DataFrame(result)


def app() -> None:
  st.title("CR-V longitudinal tuning")
  route_files = sorted(CACHE.glob("*.parquet"), reverse=True)
  if not route_files:
    st.error("No extracted routes found. Run extract_logs.py first.")
    return

  routes = [p.stem for p in route_files]
  route = st.sidebar.selectbox("Route", routes)
  behavior = st.sidebar.radio("View", ["Full route", "Stop-and-go", "Highway"])
  frame, metadata = load_route(route)
  route_start = datetime.fromisoformat(metadata["route_start_local"]) if metadata.get("route_start_local") else None
  windows = route_events(frame, behavior)

  if behavior == "Full route":
    selected = windows[0]
  elif windows:
    labels = [f"{i + 1}: {a:.0f}–{b:.0f} s" for i, (a, b) in enumerate(windows)]
    selected = windows[st.sidebar.selectbox("Event", range(len(labels)), format_func=lambda i: labels[i])]
  else:
    st.warning(f"No {behavior.lower()} windows detected in this route.")
    selected = (float(frame["time"].iloc[0]), float(frame["time"].iloc[-1]))

  pad = 5 if behavior != "Full route" else 0
  shown = frame[frame["time"].between(max(0, selected[0] - pad), selected[1] + pad)].copy()

  overshoot, speed_std, extrema = oscillation_metrics(frame)
  low_speed = frame[(frame["long_active"].fillna(False)) & (frame["v_ego"] < 2) & frame["lead_status"].fillna(False)]
  cols = st.columns(4)
  cols[0].metric("Route duration", f"{frame['time'].iloc[-1]:.0f} s")
  cols[1].metric("Low-speed minimum lead distance", f"{low_speed['d_rel'].min():.2f} m" if len(low_speed) else "n/a")
  cols[2].metric("Cruise-only peak overshoot", f"{overshoot:.2f} mph" if np.isfinite(overshoot) else "n/a")
  cols[3].metric("Cruise oscillation extrema", str(extrema))

  st.caption(
    f"{metadata.get('car_fingerprint', 'unknown car')} · sunnypilot {metadata.get('software_version', '?')} · "
    f"{metadata.get('git_branch', '?')} @ {metadata.get('git_commit', '')[:8]} · "
    f"20 Hz extraction · stock Bosch crossover reconstructed at −0.20 m/s²"
  )

  regions = {
    "Stop-and-go": route_events(frame, "Stop-and-go"),
    "Highway": route_events(frame, "Highway"),
  }
  st.plotly_chart(main_figure(shown, route_start, regions), width="stretch", config={"displaylogo": False, "scrollZoom": False})

  map_fig = gps_figure(shown, regions)
  if map_fig is not None:
    st.plotly_chart(map_fig, width="stretch", config={"displaylogo": False, "scrollZoom": False})
  else:
    st.info("No GPS fix is available in the selected window.")

  stop_windows = route_events(frame, "Stop-and-go")
  highway_windows = route_events(frame, "Highway")
  tab1, tab2 = st.tabs(["Detected stop-and-go windows", "Detected highway windows"])
  with tab1:
    st.dataframe(event_table(frame, stop_windows, "Stop-and-go"), width="stretch", hide_index=True)
  with tab2:
    st.dataframe(event_table(frame, highway_windows, "Highway"), width="stretch", hide_index=True)

  with st.expander("Signal definitions"):
    st.markdown(
      "- **Planner input:** `longitudinalPlan.accels[0]`, planned speed, lead state and source.\n"
      "- **Controller:** P/I/feedforward terms and `carControl.actuators.accel`.\n"
      "- **Honda output:** `carOutput.actuatorsOutput.accel/gas`; brake request reconstructed from the stock −0.20 m/s² crossover.\n"
      "- **Vehicle response:** `carState.vEgo/aEgo`.\n"
      "- **Following:** model lead distance/relative velocity and the MPC steady-state desired distance."
    )


if __name__ == "__main__":
  app()
