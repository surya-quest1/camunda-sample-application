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

