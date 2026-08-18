#!/usr/bin/env bash
# Runs the REAL Go assessment-tool's "assess" subcommand against the local
# cluster, then checks the resulting assessment-report.json against
# expected/coverage_manifest.json (scripts/verify.py).
#
# The binary is built read-only from the shinro repo (go build -o <here>,
# never touches shinro's own tree). Named after the host's own OS/arch (via
# `go env GOOS`/`GOARCH`) so this works unmodified on any machine -- e.g.
# assessment-tool-darwin-arm64 on a Mac, assessment-tool-linux-arm64 on a
# Jetson -- without ever needing cross-compilation flags.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHINRO_ASSESSMENT_TOOL_SRC="${SHINRO_ASSESSMENT_TOOL_SRC:-$HERE/../shinro/tools/camunda/assessment-tool}"
GOOS="$(go env GOOS)"
GOARCH="$(go env GOARCH)"
BINARY="$HERE/scripts/assessment-tool-${GOOS}-${GOARCH}"

BASE_URL="${ZEEBE_REST_ADDRESS:-http://localhost:8088}"
TOKEN_URL="${CAMUNDA_OAUTH_URL:-http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token}"
CLIENT_ID="${CAMUNDA_CLIENT_ID:-orchestration}"
AUDIENCE="${CAMUNDA_TOKEN_AUDIENCE:-orchestration-api}"
export CAMUNDA_CLIENT_SECRET="${CAMUNDA_CLIENT_SECRET:-secret}"

REPORT_PATH="$HERE/expected/actual-assessment-report.json"

log() { echo "[verify] $*" >&2; }

if [ ! -x "$BINARY" ]; then
  log "assessment-tool binary not found at $BINARY -- building from $SHINRO_ASSESSMENT_TOOL_SRC (read-only: go build -o, never touches shinro's tree)..."
  ( cd "$SHINRO_ASSESSMENT_TOOL_SRC" && go build -o "$BINARY" . )
fi

log "running assess against $BASE_URL (this walks the whole estate -- may take a few minutes)..."
"$BINARY" assess \
  --base-url "$BASE_URL/v2" \
  --auth-mode oidc \
  --oidc-token-url "$TOKEN_URL" \
  --oidc-client-id "$CLIENT_ID" \
  --oidc-audience "$AUDIENCE" \
  --output "$REPORT_PATH"

log "assess complete, report at $REPORT_PATH"
log "checking coverage against expected/coverage_manifest.json..."
python3 "$HERE/scripts/verify.py" "$REPORT_PATH"
