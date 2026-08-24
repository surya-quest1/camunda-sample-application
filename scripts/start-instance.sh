#!/usr/bin/env bash
# Start a single process instance on the local Northwind cluster.
#
# Usage:
#   bash scripts/start-instance.sh <processDefinitionId> ['<variables-json>']
#
# Examples:
#   bash scripts/start-instance.sh complaint-handling '{"complaintId":"CMP-1","channel":"email"}'
#   bash scripts/start-instance.sh sanctions-screening '{"customerId":"C-1","customerName":"A B","country":"GB"}'
#
# Multi-tenancy is on, so tenantId=<default> is always sent. Retries a few
# times to ride out broker backpressure (RESOURCE_EXHAUSTED/503) on a
# memory-constrained cluster.
set -euo pipefail

PROC_ID="${1:?usage: start-instance.sh <processDefinitionId> ['<variables-json>']}"
# NB: don't inline a {} default in the expansion -- ${2:-{}} mis-parses the
# closing brace and appends a stray '}' when $2 ends in '}'.
if [ "$#" -ge 2 ]; then VARS_JSON="$2"; else VARS_JSON='{}'; fi

BASE_URL="${BASE_URL:-http://localhost:8088}"
TOKEN_URL="${TOKEN_URL:-http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token}"
CLIENT_ID="${ORCHESTRATION_CLIENT_ID:-orchestration}"
CLIENT_SECRET="${ORCHESTRATION_CLIENT_SECRET:-secret}"

TOKEN="$(curl -fsS -X POST "$TOKEN_URL" \
  -d grant_type=client_credentials -d "client_id=$CLIENT_ID" -d "client_secret=$CLIENT_SECRET" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"

BODY="$(NI_PROC="$PROC_ID" NI_VARS="$VARS_JSON" python3 -c '
import os, json
print(json.dumps({"processDefinitionId": os.environ["NI_PROC"], "tenantId": "<default>",
                  "variables": json.loads(os.environ["NI_VARS"])}))')"

for attempt in 1 2 3 4 5 6 7 8; do
  RESP="$(curl -s -o /tmp/ni_resp.json -w '%{http_code}' -X POST "$BASE_URL/v2/process-instances" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$BODY")"
  if [ "$RESP" = "200" ]; then
    python3 -c 'import json
d=json.load(open("/tmp/ni_resp.json"))
print("started {} v{}  instanceKey={}".format(d["processDefinitionId"], d["processDefinitionVersion"], d["processInstanceKey"]))'
    exit 0
  fi
  # 503 (broker backpressure) and 500 (transient JWKS fetch timeout under load)
  # are worth retrying. A 409 INVALID_STATE (e.g. no 'none' start event) is
  # permanent -- fail fast.
  if [ "$RESP" != "503" ] && [ "$RESP" != "500" ]; then
    echo "[start-instance] HTTP $RESP (not retryable):" >&2; cat /tmp/ni_resp.json >&2; echo >&2; exit 1
  fi
  echo "[start-instance] attempt $attempt: HTTP $RESP transient, retrying..." >&2
  sleep 3
done
echo "[start-instance] failed after retries; last response:" >&2
cat /tmp/ni_resp.json >&2; echo >&2
exit 1
