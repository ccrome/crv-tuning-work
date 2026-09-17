#!/usr/bin/env bash
set -euo pipefail

dashboard_root="/home/caleb/openpilot/log-dashboard"
export PYTHONPATH="/home/caleb/openpilot/sunnypilot"
exec /home/caleb/openpilot/.venv-log-dashboard/bin/python -m streamlit run \
  "$dashboard_root/app.py" --server.address 0.0.0.0 --server.port 8501
