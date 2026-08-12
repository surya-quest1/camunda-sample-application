# Northwind Private Bank — Reference Application

A deliberately production-shaped Camunda 8 estate built to exercise the Shinro
Camunda → Temporal **assessment tool** end to end. Standalone project — not
part of, and never imported into, the `shinro` repository.

See `../shinro/camunda_to_temporal_docs/reference-application/` for the design
docs (`00_design_proposal.md`, `01_coverage_matrix.md`,
`02_application_walkthrough.md`) — the business narrative, the dependency
map, and why the estate is shaped the way it is. This README is the
*operational* companion: how to actually stand it up.

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

## What's built and verified (2026-08-12)

Confirmed by actually running each step against a live cluster, not just
generated:

- **All 16 processes + 3 DMN (5 decisions across 2 DRDs) + 5 forms deploy
  cleanly** — `bash scripts/deploy.sh` runs end to end with no errors.
- **Construct coverage: 46 of 48 classification-table keys** hit by the 16
  processes alone (verified by running the real `pkg/mapper.Classify`
  against every generated file — see `scripts/bpmn-validate -classify`).
  The 2 misses (`gateway.complex`, `conditionalEvent`) can never execute in
  Zeebe by design; see `docs/spike-results/two-pool-spike-RESULTS.md` for
  whether static inventory coverage is reachable instead.
- **Both worker services start and register cleanly against the live
  cluster** (22 Java job types, 10 Python job types — matches the design's
  job-type split exactly).
- **Clock control confirmed**: pinning the broker clock backdates
  `startDate` on real instance records, exactly as the seeding plan
  requires — see `docs/spike-results/clock-control-RESULTS.md`.
- **fx-settlement deployed at 3 real versions** (content-distinct v1/v2/v3,
  not just re-deploys) — the version-skew construct for gap #4.
- **Multi-tenancy**: `retail` / `private-bank` tenants created, orchestration
  client assigned to both, a process subset deployed tenant-scoped.

### Bugs found and fixed along the way (all confirmed against the live cluster)

1. **Zeebe 8.8.34 crashes with an internal NPE** ("Cannot invoke
   `String.getBytes` because value is null") when a `<bpmn:compensateEventDefinition>`
   has no `id` attribute, instead of a clean validation error. Fixed by
   giving every event definition an explicit id (`bpmn_builder.py`).
2. **DMN `aggregation="NONE"`** is not a valid `BuiltinAggregator` value —
   the DMN 1.3 spec's default (no aggregation) is expressed by omitting the
   attribute entirely, not setting it to the string "NONE". Fixed in
   `credit-risk.dmn`.
3. **Zeebe's `EventBasedGatewayValidator`** resolves a gateway's outgoing
   flows via explicit `<bpmn:incoming>`/`<bpmn:outgoing>` child elements
   (the BPMN-spec convention, normally written by every visual modelling
   tool), not by scanning sibling `sequenceFlow` `sourceRef`/`targetRef`
   attributes the way other gateway types tolerate. Fixed centrally in
   `bpmn_builder.py`'s `tostring()` as a tree-wide post-processing pass.
4. **pyzeebe's oauth channel is event-loop-sensitive**: constructing
   `ZeebeWorker` at Python module-import time (before `asyncio.run()`
   creates the loop `main()` runs under) produces
   `RuntimeError: Task ... attached to a different loop` at runtime. Fixed
   by deferring worker construction into `main()` and switching task
   modules to a `register(worker)` pattern instead of import-time
   decorators on a module-level singleton.
5. **`requests_oauthlib` refuses cleartext OAuth2** token requests
   (`InsecureTransportError`) — needs `OAUTHLIB_INSECURE_TRANSPORT=1` for
   this local, non-TLS cluster.
6. **Two BPMN variable-scope bugs of my own**: `document-collection`'s
   message correlation key referenced `documentRef`, a variable no caller
   ever provided (fixed to correlate on `applicationId`, which is in scope
   everywhere it's called from); `identity-verification` referenced
   `applicantRef`, which `customer-onboarding-kyc`'s multi-instance call
   activity never mapped in (fixed by deriving it via
   `=applicant.ref` in the io-mapping).
7. **Escalation boundary events can only attach to a subprocess or call
   activity**, not a plain task — `credit-bureau-assessment`'s DMN
   evaluation task had to be wrapped in an embedded subprocess.
8. **`modelerTemplate` must be `zeebe:modelerTemplate`**, not a bare
   attribute — Zeebe's XSD rejects the unprefixed form Camunda Modeler UIs
   sometimes render it as in casual examples.
9. **BPMN artifacts (`<bpmn:association>`) must be declared after every
   flow element**, not interleaved — Zeebe's XSD enforces `tProcess`'s
   strict content-model sequence.
10. **Message throw/end events need an explicit `zeebe:taskDefinition`**
    (or `zeebe:publishMessage`) extension in Zeebe 8.8 — a bare
    `messageEventDefinition` is no longer sufficient for a throw position.
11. **Camunda's OOTB `io.camunda:http-json:1` connector reads its config
    from `zeebe:ioMapping` input variables, not `zeebe:taskHeaders`** — the
    job-worker pattern used everywhere else in this codebase. Authoring it
    as taskHeaders produces a live `JOB_NO_RETRIES` failure
    (`method`/`url` "must not be null"). Fixed in `svc_pull_report`
    (`gen_p03_p04_p05.py`); confirmed against the live cluster and by a
    subsequent `verify.sh` pass.

None of these were guessed — each was isolated with a minimal reproduction
deployed to the real cluster before being fixed. See git history / this
file for the specific commits.

### End-to-end smoke test (2026-08-12)

With both workers running against a freshly-deployed cluster: started
instances across 6 processes (`identity-verification`,
`sanctions-screening`, `credit-bureau-assessment`, `customer-onboarding-kyc`,
`fx-settlement`, plus a full-variable retest). `sanctions-screening` and
`fx-settlement` **completed with zero incidents**. With a complete variable
set, `identity-verification` → `document-collection` (its call-activity
child) also ran **incident-free**, confirming the two variable-scope fixes
above are correct and sufficient — the incidents seen on an earlier,
incomplete-variable smoke run were test-data gaps, not further BPMN bugs
(confirmed by re-running with the missing variables supplied).

### Known remaining gap

- **`property-valuation-scheduling` has no `none` start event** by design
  (only a timer-cycle start) — cannot be instance-created directly via
  `POST /v2/process-instances`; runs on its own nightly schedule. Not a
  bug, just means the seeding driver must let its own timer fire rather
  than starting it manually.

## Status — what's left

Per the design doc's phases (`REF APP - SEEDING`, `INTEGRATION`,
`VERIFICATION`, `TOOL FIXES`):

- **Seeding driver** (`seed/run_seed.py`) is complete: a reproducible,
  parameterized 45-day simulated-time loop (Poisson-sampled per-process
  cohorts, signal broadcasts, message correlation, user-task completion,
  clock pin/reset per day) — `--seed 42 --days 45` against a fresh estate
  produced 2847 instances across 46 simulated days plus one deliberately
  never-completed long-running seed instance. Fully re-runnable against any
  cluster (see `docs/JETSON_SETUP.md` for running it on a new machine).
- **`scripts/verify.sh` + `scripts/verify.py`** (automated pass/fail
  against the real assessment tool's output, checked against
  `expected/coverage_manifest.json`) are built and passing **14/14 checks,
  0 failures, 1 expected warning**.
- **TOOL FIXES** (the 3 assessment-tool defects found during design —
  call-hierarchy not surfaced, `CallActivityInputResolution` dropped,
  `Parse()` takes the first process) have been applied directly to
  `shinro`'s `tools/camunda/assessment-tool` (build clean, full existing
  test suite passing). The unified-diff patch set that was staged in this
  repo has been removed now that it's merged upstream.
- **Jetson re-validation**: see `docs/JETSON_SETUP.md` for the full
  bring-up procedure (prerequisites, cluster start, estate deploy, worker
  start, seed re-run, assessment-tool run) — not yet executed on real
  Jetson hardware, but the procedure is fully documented and every script
  it depends on has been verified on this dev machine.
