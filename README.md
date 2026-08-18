# Northwind Private Bank — Reference Application

A deliberately production-shaped Camunda 8 estate built to exercise the Shinro
Camunda → Temporal **assessment tool** end to end.
![arch](https://github.com/surya-quest1/camunda-sample-application/blob/main/architecture.png)
## What's here

```
cluster/          Camunda 8.8 full docker-compose bundle (vendored from
                   camunda/camunda-distributions), local-only config
models/           16 BPMN processes, 3 DMN decisions, 5 forms
fixtures/         F01/F02 -- constructs Zeebe cannot execute (analyser
                   unit-fixture-only; see docs/spike-results/two-pool-spike)
workers-java/     Spring Boot + spring-zeebe job workers (22 job types)
workers-python/   pyzeebe job workers (10 job types)
scripts/          BPMN generator (Python + bpmn_builder.py), bpmn-validate
                   (Go, links the real assessment-tool analyser), deploy.sh
seed/             Reproducible 45-day simulated-time seeding driver
                   (run_seed.py), clock control, REST API client
expected/         coverage_manifest.json + the real tool's actual output
docs/spike-results/  Findings from live-cluster spikes: two-pool deploy,
                   clock control
docs/JETSON_SETUP.md  How to stand this whole app up on a new machine
                   (prereqs, bring-up, re-seeding, verification)
```

## Quick start

```bash
# 1. Bring up the cluster (needs ~10GB Docker Desktop memory -- see below)
cd cluster && docker compose -f docker-compose-full.yaml up -d
# wait for all 13 containers healthy: docker compose -f docker-compose-full.yaml ps

# 2. (Re)generate the BPMN, then add diagram layout -- see "Diagrams in
#    Operate" below for why step 2b exists
cd .. && for s in scripts/gen_*.py; do python3 "$s"; done
cd scripts/bpmn-auto-layout && npm install && node layout.mjs && cd ../..

# 3. Deploy the estate
bash scripts/deploy.sh

# 4. Start the workers (separate terminals)
cd workers-java && mvn spring-boot:run
cd workers-python && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  OAUTHLIB_INSECURE_TRANSPORT=1 .venv/bin/python -m northwind_workers.main
```

### Diagrams in Operate

`bpmn_builder.py` generates semantic-only BPMN — no `bpmndi:BPMNDiagram`
layout data — because the assessment tool's analyser never reads it.
Operate's process viewer does, though: without it, every process renders
as a blank canvas (diagram-less, but otherwise fully functional — instance
list, variables, incidents all still work).

Fixed by running every generated file through bpmn-io's own
**`bpmn-auto-layout`** (`scripts/bpmn-auto-layout/layout.mjs`) before
deploying — confirmed to add *only* `bpmndi:*`/`dc:*`/`di:*` elements,
verified by diffing the real analyser's census output before and after
(byte-identical). This is now step 2b in Quick Start, not optional; the
estate currently deployed is at **v2** for exactly this reason (v1 was the
semantic-only deploy from initial verification, before this was added).

Operate: http://localhost:8088/operate · Tasklist: http://localhost:8088/tasklist
Identity: http://localhost:8088/identity · Keycloak: http://localhost:18080/auth

Default OIDC client: `orchestration` / `secret` (from `cluster/.env`).

## Docker Desktop memory

The full bundle (13 containers: orchestration, connectors, Elasticsearch,
Identity, Keycloak, Optimize, Web Modeler ×3, Postgres ×2, Console, Mailpit)
needs more than Docker Desktop's 4GB default -- it OOM-kills Elasticsearch
under that. Set **Docker Desktop → Settings → Resources → Memory to 10GB+**
before bringing the stack up (this machine has 18GB; raised to 10GB/6 CPUs).

## Multi-tenancy

On by default (`.env`: `CAMUNDA_SECURITY_MULTITENANCY_CHECKSENABLED=true`).
Every deploy/create-instance call needs an explicit `tenantId` — the
default tenant's literal ID is the string `<default>` (with angle brackets).
`scripts/deploy.sh` handles this; if calling the API directly with `curl -F`,
use `--form-string "tenantId=<default>"`, not `-F` (curl's `-F` treats a
leading `<` as "read this field's value from a file").

## Deploying to Camunda SaaS

The estate is dual-target: every script, worker, and the seed driver read
their cluster endpoints and credentials from environment variables with
local-cluster defaults, so pointing the same code at Camunda SaaS is just a
set of exports — no code changes, no separate branch.

### Prerequisites in Camunda Console

1. **Create a cluster** (8.8.x to match `workers-java/pom.xml`'s
   `version.camunda`). Multi-tenancy is on by design in this estate, so
   create a **multi-tenant** cluster — it's a creation-time setting and
   can't be flipped later.
2. **Create an API client** (Console → cluster → API tab) with Deployment +
   Read + Write permissions on Zeebe. Note the **Client ID**, **Client
   Secret**, and the **Zeebe audience** Console shows (region-scoped).
3. Note the **Cluster ID**, **Region** (e.g. `bru-2`), and the **REST base
   URL** and **gRPC address** from Console's API tab (Gen1 vs Gen2 clusters
   have different URL shapes — copy them from Console rather than guessing).

### Environment exports

```bash
export CAMUNDA_CLIENT_MODE=saas
export CAMUNDA_CLIENT_CLOUD_CLUSTERID=<from Console>
export CAMUNDA_CLIENT_CLOUD_REGION=<e.g. bru-2>
export CAMUNDA_CLIENT_ID=<api client id>
export CAMUNDA_CLIENT_SECRET=<api client secret>
export CAMUNDA_TOKEN_AUDIENCE=<zeebe audience from Console>
export CAMUNDA_OAUTH_URL=https://login.cloud.camunda.io/oauth/token
export DEFAULT_TENANT_ID=<Console-assigned default tenant ID>
# REST base URL for deploy.sh + seed driver -- copy from Console's API tab:
export ZEEBE_REST_ADDRESS=https://<region>.zeebe.camunda.io/<cluster-id>    # Gen1
# or: https://api.<region>.zeebe.camunda.io/<cluster-id>                   # Gen2
# gRPC address for the Python workers (TLS host, not localhost):
export ZEEBE_GRPC_ADDRESS=<cluster-id>.<region>.zeebe.camunda.io:443
```

### Deploy + run workers + seed

```bash
# 1. Deploy the estate (idempotent)
bash scripts/deploy.sh

# 2. Java workers -- saas mode tells spring-zeebe to derive endpoints
#    from cloud.cluster-id + cloud.region (the *_ADDRESS / token-url
#    defaults in application.yaml are ignored in saas mode)
cd workers-java && mvn spring-boot:run

# 3. Python workers -- no OAUTHLIB_INSECURE_TRANSPORT (that's local-only);
#    worker_setup.py auto-detects TLS from ZEEBE_GRPC_ADDRESS
cd workers-python && .venv/bin/python -m northwind_workers.main

# 4. Seed driver (picks up ZEEBE_REST_ADDRESS / CAMUNDA_OAUTH_URL /
#    CAMUNDA_CLIENT_ID / CAMUNDA_CLIENT_SECRET from env automatically;
#    CLI flags still override if you need to differ)
.venv/bin/python seed/run_seed.py --days 45 --seed 42

# 5. Assessment tool
bash scripts/verify.sh
```

### What does NOT work on SaaS

**Clock control (`seed/clock.py`) is a self-managed-only API.** The
`PUT /v2/clock` endpoint that pins the broker's engine clock is disabled on
Camunda SaaS, so the seed driver's simulated-past design (45 days of
backdated, pinned-clock history) will not work against SaaS regardless of
configuration. `run_seed.py` will run but every `clock.pin*` call will fail
and instances get real-time timestamps instead of backdated ones.

If backdated history is the point of this estate (and the README's
"reproducible 45-day simulated-time seeding" framing suggests it is),
self-managed is the correct target. SaaS works for live/forward-only
demos and worker validation, but not for the assessment tool's
historical-window scan.

### What's different from local, at a glance

| Thing | Local | SaaS |
|---|---|---|
| Java worker mode | `self-managed` (default) | `CAMUNDA_CLIENT_MODE=saas` |
| Python worker TLS | plaintext (`grpc.local_channel_credentials`) | TLS (auto-detected from address) |
| `OAUTHLIB_INSECURE_TRANSPORT` | `1` (required) | unset |
| Token URL | Keycloak `localhost:18080` | `login.cloud.camunda.io/oauth/token` |
| Default tenant ID | `<default>` (literal) | Console-assigned (override `DEFAULT_TENANT_ID`) |
| Clock control | works (`PUT /v2/clock`) | **disabled** — seed driver can't pin |

