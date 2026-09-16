#!/usr/bin/env bash
# Copy complete rlogs for explicitly named Comma routes into the local dataset.
set -euo pipefail

comma_host="${COMMA_HOST:-192.168.86.31}"
comma_user="${COMMA_USER:-comma}"
comma_key="${COMMA_SSH_KEY:-/home/caleb/.ssh/id_rsa}"
remote_root="/data/media/0/realdata"
local_root="${LOCAL_LOG_ROOT:-/home/caleb/openpilot/route-data}"
dry_run=""

usage() {
  cat <<'EOF'
Usage: sync-comma-rlogs.sh [--dry-run] ROUTE [ROUTE ...]

Copies rlog.zst and qlog.zst from complete route segments on the Comma.
Routes must be explicit, for example: 0000005e--0123456789

Optional environment variables:
  COMMA_HOST       Device IP or hostname (default: 192.168.86.31)
  COMMA_USER       SSH user (default: comma)
  COMMA_SSH_KEY    SSH private-key path (default: /home/caleb/.ssh/id_rsa)
  LOCAL_LOG_ROOT   Destination (default: /home/caleb/openpilot/route-data)
EOF
}

if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run="--dry-run"
  shift
fi
if [[ "$#" -eq 0 ]]; then
  usage >&2
  exit 2
fi
if [[ ! -r "$comma_key" ]]; then
  echo "SSH key is not readable: $comma_key" >&2
  exit 2
fi

mkdir -p "$local_root"
for route in "$@"; do
  if [[ ! "$route" =~ ^[[:xdigit:]]{8}--[[:xdigit:]]{10}$ ]]; then
    echo "Invalid route prefix: $route" >&2
    exit 2
  fi
  echo "Syncing $route from $comma_user@$comma_host"
  rsync -a --progress $dry_run \
    --include='*/' --include='rlog.zst' --include='qlog.zst' --exclude='*' \
    -e "ssh -i $comma_key" \
    "$comma_user@$comma_host:$remote_root/$route--*/" "$local_root/"
done
