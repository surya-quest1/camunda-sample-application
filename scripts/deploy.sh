#!/usr/bin/env bash
# Deploys the Northwind Private Bank estate to a Camunda 8.8 cluster:
#   1. Fetches an OIDC client-credentials token (Keycloak for self-managed,
#      login.cloud.camunda.io for SaaS).
#   2. Deploys all base resources (16 BPMN + 3 DMN + 5 forms) in one atomic call.
#   3. Deploys fx-settlement v2 then v3 (separate calls, in order, so Zeebe assigns
#      versions 2 and 3 to the same processId -- P16's version-skew design).
#   4. If MULTI_TENANCY=true: creates the retail / private-bank
#      tenants, assigns the client to both, and deploys a tenant-scoped subset
#      into each (D6 -- multi-tenancy). Skipped entirely on single-tenant clusters.
#
# Idempotent: Zeebe dedupes identical resource content by checksum, so
# re-running this script is safe (won't mint spurious extra versions).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="$HERE/models"

BASE_URL="${ZEEBE_REST_ADDRESS:-http://localhost:8088}"
TOKEN_URL="${CAMUNDA_OAUTH_URL:-http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token}"
CLIENT_ID="${CAMUNDA_CLIENT_ID:-orchestration}"
CLIENT_SECRET="${CAMUNDA_CLIENT_SECRET:-secret}"
AUDIENCE="${CAMUNDA_TOKEN_AUDIENCE:-orchestration-api}"
# Multi-tenancy is on by design in this estate (D6), but SaaS clusters are
# typically single-tenant. Set MULTI_TENANCY=true to create the retail /
# private-bank tenants and deploy a tenant-scoped subset into each.
# Defaults to false (single-tenant) so it works out of the box on SaaS;
# set to true for the local docker-compose cluster (which has multi-tenancy
# enabled in cluster/.env).
MULTI_TENANCY="${MULTI_TENANCY:-false}"

log() { echo "[deploy] $*" >&2; }

fetch_token() {
  # Camunda SaaS OAuth requires an `audience` parameter (the Zeebe audience
  # from Console); local Keycloak ignores it. Sending it unconditionally
  # works for both targets.
  curl -fsS -X POST "$TOKEN_URL" \
    -d "grant_type=client_credentials" \
    -d "client_id=$CLIENT_ID" \
    -d "client_secret=$CLIENT_SECRET" \
    -d "audience=$AUDIENCE" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
}

log "fetching OIDC token from $TOKEN_URL..."
TOKEN="$(fetch_token)"
log "token acquired"

auth_curl() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$@"
}

# Multi-tenancy is on by default (D6), so every deployment call needs a
# tenantId form field. <default> is the literal tenant ID a self-managed
# cluster seeds automatically; on SaaS multi-tenant the default tenant ID
# is assigned by Console and varies -- override via DEFAULT_TENANT_ID. Use
# --form-string (not -F) so curl doesn't interpret a leading '<' as "read
# this field's value from a file".
# On single-tenant clusters (MULTI_TENANCY=false), no tenantId is sent at
# all -- the engine assigns the default tenant implicitly.
DEFAULT_TENANT_ID="${DEFAULT_TENANT_ID:-<default>}"
if [ "$MULTI_TENANCY" = "true" ]; then
  DEFAULT_TENANT_ARGS=(--form-string "tenantId=$DEFAULT_TENANT_ID")
else
  DEFAULT_TENANT_ARGS=()
fi
# set -u treats an empty array as unbound when expanded with [@]; ${arr[@]+"${arr[@]}"} is
# the bash idiom that expands to nothing if the array is empty, without triggering -u.

# --- 1. Base estate: 16 BPMN + 3 DMN + 5 forms, one atomic deployment -------
log "deploying base estate (16 BPMN + 3 DMN + 5 forms)..."
RESOURCE_ARGS=()
for f in "$MODELS_DIR"/*.bpmn "$MODELS_DIR"/*.dmn "$MODELS_DIR"/*.form; do
  base="$(basename "$f")"
  # Skip the version-variant and spike files -- deployed separately below.
  case "$base" in
    fx-settlement-v2.bpmn|fx-settlement-v3.bpmn|two-pool-spike.bpmn) continue ;;
  esac
  RESOURCE_ARGS+=(-F "resources=@$f;filename=$base")
done
DEPLOY_RESULT="$(auth_curl -X POST "$BASE_URL/v2/deployments" ${DEFAULT_TENANT_ARGS[@]+"${DEFAULT_TENANT_ARGS[@]}"} "${RESOURCE_ARGS[@]}")"
echo "$DEPLOY_RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for dep in d.get('deployments', []):
    if not dep:
        continue
    for kind in ('processDefinition', 'decisionDefinition', 'decisionRequirements', 'form'):
        if kind in dep:
            r = dep[kind]
            if not r:
                continue
            ident = r.get('processDefinitionId') or r.get('dmnDecisionId') or r.get('formId') or '?'
            print(f\"  {kind}: {ident} v{r.get('version','?')}\")
"

# --- 2. fx-settlement v2, then v3 (order matters -- creates versions 2, 3) --
log "deploying fx-settlement v2..."
auth_curl -X POST "$BASE_URL/v2/deployments" ${DEFAULT_TENANT_ARGS[@]+"${DEFAULT_TENANT_ARGS[@]}"} \
  -F "resources=@$MODELS_DIR/fx-settlement-v2.bpmn;filename=fx-settlement.bpmn" >/dev/null
log "deploying fx-settlement v3..."
auth_curl -X POST "$BASE_URL/v2/deployments" ${DEFAULT_TENANT_ARGS[@]+"${DEFAULT_TENANT_ARGS[@]}"} \
  -F "resources=@$MODELS_DIR/fx-settlement-v3.bpmn;filename=fx-settlement.bpmn" >/dev/null
log "fx-settlement now at 3 versions (v1 base + v2 + v3)"

# --- 3. Tenants (D6 -- multi-tenancy, skipped if MULTI_TENANCY=false) --------
if [ "$MULTI_TENANCY" = "true" ]; then
  create_tenant() {
    local tenant_id="$1" name="$2"
    log "creating tenant $tenant_id..."
    auth_curl -X POST "$BASE_URL/v2/tenants" \
      -H "Content-Type: application/json" \
      -d "{\"tenantId\": \"$tenant_id\", \"name\": \"$name\"}" >/dev/null 2>&1 \
      || log "  (tenant $tenant_id may already exist -- continuing)"
  }
  create_tenant "retail" "Retail Banking"
  create_tenant "private-bank" "Private Banking"

  assign_client_to_tenant() {
    local tenant_id="$1" client_id="$2"
    auth_curl -X PUT "$BASE_URL/v2/tenants/$tenant_id/clients/$client_id" >/dev/null 2>&1 \
      || log "  (client $client_id may already be assigned to $tenant_id -- continuing)"
  }
  assign_client_to_tenant "retail" "$CLIENT_ID"
  assign_client_to_tenant "private-bank" "$CLIENT_ID"
  log "orchestration client assigned to both tenants"

  # --- 4. Tenant-scoped subset: loan-application + its direct children -------
  # Deploys the flagship process (and the children it calls) into each tenant
  # explicitly, so FetchMultiTenancyIdentity finds tenant-scoped resources,
  # not just tenant/identity scaffolding with nothing deployed under it.
  TENANT_SUBSET=(loan-application customer-onboarding-kyc identity-verification
                 sanctions-screening credit-bureau-assessment document-collection)

  deploy_subset_to_tenant() {
    local tenant_id="$1"
    log "deploying tenant-scoped subset to $tenant_id..."
    local args=()
    for name in "${TENANT_SUBSET[@]}"; do
      args+=(-F "resources=@$MODELS_DIR/$name.bpmn;filename=$name.bpmn")
    done
    auth_curl -X POST "$BASE_URL/v2/deployments" --form-string "tenantId=$tenant_id" "${args[@]}" >/dev/null
  }
  deploy_subset_to_tenant "retail"
  deploy_subset_to_tenant "private-bank"
else
  log "MULTI_TENANCY=false -- skipping tenant creation and tenant-scoped deploys"
fi

log "deploy complete."
