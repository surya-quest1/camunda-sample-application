# Portable setup — standing this up on a new machine (Jetson)

This is the machine-to-machine setup guide: how to take everything in this
repo and stand up an identical, independently-seeded Camunda 8 estate on a
different host — the target case being an NVIDIA Jetson (aarch64 / Ubuntu,
Linux ARM64). The root [README.md](../README.md) is the reference for *what*
is built and *why*; this doc is only the *how* for a fresh machine.

Nothing here requires touching the `shinro` repo. This repo's own scripts
build a read-only Go binary from a **sibling checkout** of `shinro` — they
never write into it.

## What has to travel to the new machine

| Item | How |
|---|---|
| This repo (`northwind-reference-app/`) | `git clone` / `rsync` / `scp -r` |
| A `shinro` checkout, as a **sibling directory** (`../shinro` relative to this repo) | `git clone` — only needed for `scripts/verify.sh` to build the assessment-tool binary from source; nothing else in this repo depends on it |
| `cluster/.env` | **Not in git** (gitignored — it holds real OIDC client secrets and DB passwords). Copy it explicitly: `scp` it over, or hand-author a new one using the template below |

Everything else (BPMN generator, seed driver, workers, docker-compose bundle)
is plain source and travels with a normal clone.

### `cluster/.env` — what it needs

The file is gitignored on purpose (it holds live secrets for local dev), so
it won't come along with a plain `git clone`. Two options:

1. **Copy the working file directly** (simplest, keeps identical secrets —
   fine for a local/lab deployment): `scp dev-machine:northwind-reference-app/cluster/.env jetson:northwind-reference-app/cluster/.env`
2. **Author a fresh one.** It needs, at minimum:
   - Image version pins (`CAMUNDA_VERSION=8.8.34`, `CAMUNDA_CONNECTORS_VERSION`, `CAMUNDA_IDENTITY_VERSION`, etc. — copy these unmodified, they're not secrets)
   - `ORCHESTRATION_CLIENT_ID=orchestration`, `ORCHESTRATION_CLIENT_SECRET=<pick a value>` — this is the credential every script in this repo (`deploy.sh`, `verify.sh`, `seed/run_seed.py`, both worker services) authenticates with; if you change it from the default `secret`, you must pass the same value to every script below via `--client-secret` / `ORCHESTRATION_CLIENT_SECRET` / `CAMUNDA_OIDC_CLIENT_SECRET`
   - `CAMUNDA_SECURITY_MULTITENANCY_CHECKSENABLED=true`, `CAMUNDA_SECURITY_MULTITENANCY_APIENABLED=true` (multi-tenancy is on by design in this estate)
   - The Identity/Keycloak/Web-Modeler/Console/Optimize client secrets and Postgres passwords (any values work for a local/lab stack — they just need to be internally consistent, since Keycloak and each service read the same `.env`)
   - `HOST=localhost`, `KEYCLOAK_HOST=host.docker.internal`

   Use `cluster/README.md` and `cluster/docker-compose-full.yaml` as the
   authoritative list of every variable actually referenced.

## Prerequisites on the new machine

| Tool | Version used in dev | Why | Jetson note |
|---|---|---|---|
| Docker + Docker Compose v2 | any recent | runs the Camunda 8 cluster | JetPack ships Docker; if not, install Docker Engine for Ubuntu (Jetson is standard `linux/arm64`, no special Jetson-specific Docker build needed) |
| Go | 1.26.1 (`go.mod`'s `go 1.26.1`) | builds the assessment-tool binary read-only from `shinro` source | Go's arm64 builds are native — no cross-compilation needed when building *on* the Jetson itself |
| Java 21 + Maven | pom.xml pins `java.version=21` | `workers-java` (Spring Boot / spring-zeebe, 22 job types) | any OpenJDK 21 distro for arm64 (Temurin, Amazon Corretto) |
| Python 3.12 | `workers-python/Dockerfile` base image | `workers-python` (pyzeebe, 10 job types) + all `scripts/gen_*.py` + `seed/run_seed.py` | Jetson's default Python is often older — install 3.12 via `deadsnakes`/pyenv if needed |
| Node.js (any current LTS) | — | `scripts/bpmn-auto-layout` (adds `bpmndi:*` diagram layout so Operate renders diagrams — see root README's "Diagrams in Operate") | |

Docker memory: the full 13-container bundle OOM-kills Elasticsearch under
4GB. **Give Docker at least 10GB RAM.** On a Jetson this means checking
total board RAM first — an 8GB Jetson (Orin Nano/NX 8GB) does **not** have
headroom for this; a 16GB+ Jetson (Orin NX 16GB, AGX Orin) is the realistic
minimum. There's no Docker Desktop "Resources" panel on Linux — memory is
whatever the host has, so this is really "does the board have 16GB+ RAM",
not a setting to change.

## Step-by-step bring-up

```bash
# 0. Clone both repos as siblings
git clone <shinro-remote> shinro
git clone <this-repo-remote> northwind-reference-app
# copy or author cluster/.env as described above
cp /path/to/known-good/cluster/.env northwind-reference-app/cluster/.env

# 1. Bring up the cluster
cd northwind-reference-app/cluster
docker compose -f docker-compose-full.yaml up -d
# wait for all 13 containers healthy:
docker compose -f docker-compose-full.yaml ps
```

```bash
# 2. Generate the BPMN/DMN/form estate, then add diagram layout
cd ..   # back to northwind-reference-app root
python3 -m venv .venv-gen && .venv-gen/bin/pip install -q --upgrade pip
for s in scripts/gen_*.py; do .venv-gen/bin/python3 "$s"; done

cd scripts/bpmn-auto-layout
npm install
node layout.mjs
cd ../..
```

```bash
# 3. Deploy the estate (idempotent -- safe to re-run)
bash scripts/deploy.sh
```

```bash
# 4. Start both worker services (separate terminals / systemd units / tmux panes)

# Java workers
cd workers-java
mvn spring-boot:run

# Python workers
cd workers-python
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
OAUTHLIB_INSECURE_TRANSPORT=1 .venv/bin/python -m northwind_workers.main
```

At this point Operate/Tasklist/Identity are reachable exactly as on the dev
machine: `http://<jetson-host>:8088/operate`, `.../tasklist`, `.../identity`;
Keycloak at `http://<jetson-host>:18080/auth`. (Substitute the Jetson's
actual hostname/IP for `localhost` if accessing from another machine on the
network — `HOST`/`KEYCLOAK_HOST` in `cluster/.env` control what URLs get
baked into redirects.)

## Simulating the past — re-running the seed driver

`seed/run_seed.py` is the reproducible history generator: given a seed
value, it deterministically re-creates the same *shape* of 45 simulated days
of traffic (Poisson-sampled cohorts per process, signal broadcasts, message
correlation, user-task completions) against whatever cluster you point it
at. It does **not** require the dev machine or any prior state — it's a
cold-start script that only needs a freshly-deployed, empty estate.

```bash
cd seed
python3.12 -m venv .venv && .venv/bin/pip install httpx   # the only third-party dependency; no requirements.txt here

.venv/bin/python run_seed.py \
  --days 45 \
  --seed 42 \
  --base-url http://localhost:8088 \
  --token-url http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token \
  --client-id orchestration \
  --client-secret "$ORCHESTRATION_CLIENT_SECRET"
```

Flags (all optional, shown with their defaults from `seed/run_seed.py`):

| Flag | Default | Purpose |
|---|---|---|
| `--days` | `45` | simulated days of history to produce |
| `--scale` | `1.0` | multiplier on `traffic_profile.py`'s daily rates — turn down for a quick smoke test, e.g. `--scale 0.2` |
| `--seed` | `42` | RNG seed — fixes the *shape* of the run (same cohort sizes, same signal timing) but not exact generated instance keys; use the same seed to reproduce an equivalent dataset on any cluster |
| `--base-url` | `http://localhost:8088` | point this at the Jetson's own `8088` if running the script from elsewhere on the network |
| `--token-url` | Keycloak realm token endpoint | same host substitution as above |
| `--client-id` / `--client-secret` | `orchestration` / `secret` | must match `cluster/.env`'s `ORCHESTRATION_CLIENT_ID`/`_SECRET` |
| `--dry-run` | off | prints the planned cohort/day schedule without calling the cluster — useful to sanity-check timing before committing to a real run |

This is the same script, run the same way, that produced the dev machine's
"2847 instances across 46 simulated days" result — pointing it at a fresh
Jetson cluster with the same `--seed 42 --days 45` reproduces an
equivalent-shape dataset there. A full run takes a while (it's driving real
HTTP calls against the broker for every cohort, across 45 pinned-clock days)
— expect it to run for tens of minutes on modest hardware; `--dry-run` first
if you just want to confirm the schedule.

`seed/reseed_fixes.py` is a lighter, faster **partial** reseed (7 days,
`seed=43`, 3 specific processes) — only useful if you're validating a
one-off process fix, not for the primary full-history run. It takes the
same `--base-url` / `--token-url` / `--client-id` / `--client-secret`
flags as `run_seed.py` (same defaults), so pointing it at a non-local
cluster is the same override pattern.

After a large seed completes, **wait ~60–120 seconds before running the
assessment tool** — Elasticsearch's search index lags behind the raw event
stream under burst writes (`x-eventually-consistent: true` on the search
APIs), and a scan run immediately after seeding will undercount recent
instances. This was confirmed on the dev machine: a scan run immediately
after seeding showed 17 starts where the true count was ~107, corrected on
a second run 5 minutes later.

## Running the assessment tool / verification

```bash
bash scripts/verify.sh
```

This builds `scripts/assessment-tool-<os>-<arch>` (e.g.
`assessment-tool-linux-arm64` on a Jetson) read-only from
`../shinro/tools/camunda/assessment-tool` via `go build -o`, runs `assess`
against the live cluster, and checks the output against
`expected/coverage_manifest.json`. Override
`SHINRO_ASSESSMENT_TOOL_SRC=/path/to/shinro/tools/camunda/assessment-tool`
if `shinro` isn't checked out as a direct sibling directory.

The binary name is derived from `go env GOOS`/`GOARCH` at build time, so the
same script produces a correctly-named native binary on any host — no
manual `GOOS=linux GOARCH=arm64` cross-compilation flags needed when running
the build *on* the target machine itself (which is the normal case here:
building natively on the Jetson, not cross-compiling from macOS).

## Known platform-specific notes

- **`OAUTHLIB_INSECURE_TRANSPORT=1`** is required for the Python workers
  against this non-TLS local cluster, on any host — not Jetson-specific,
  just easy to forget on a fresh setup. **Do not set it for SaaS** — SaaS
  uses TLS and the Python worker auto-detects from `ZEEBE_GRPC_ADDRESS`.
- **`--form-string`, not `-F`**, for any direct `curl` deployment call —
  the default tenant's literal ID is the string `<default>` (with angle
  brackets) on self-managed; `curl -F` misreads the leading `<` as "read
  this field from a file". `scripts/deploy.sh` already handles this via
  `DEFAULT_TENANT_ID` (env-overridable, defaults to `<default>`); only
  matters if you're crafting your own calls.
- No Jetson-specific container images are needed anywhere in this stack —
  every image in `cluster/docker-compose-full.yaml` (Camunda, Elasticsearch,
  Keycloak, Postgres, Mailpit) publishes official `linux/arm64` manifests,
  so `docker compose up` on Jetson pulls the same tags as the dev machine
  and Docker resolves the correct architecture automatically. No `--platform`
  overrides required.

## Assessment-tool fixes

The 3 assessment-tool defects found while building this reference estate
(call-hierarchy not surfaced on graph nodes, `CallActivityInputResolution`
findings dropped, `Parse()` silently parsing the wrong process in
multi-pool BPMN files) have been applied directly to `shinro`'s
`tools/camunda/assessment-tool`. Any `shinro` checkout pulled after that
change already has them — `scripts/verify.sh` on a fresh Jetson clone will
build the fixed binary with no extra steps.

## Camunda SaaS instead of self-managed

Everything above assumes the local docker-compose cluster. The same repo
also targets Camunda SaaS with no code changes — every script, worker, and
the seed driver read cluster endpoints and credentials from environment
variables with local-cluster defaults. See the root [README.md](../README.md)'s
"Deploying to Camunda SaaS" section for the full env-var list and the
prerequisites in Camunda Console (multi-tenant cluster, API client, region/
cluster IDs).

Quick summary of what changes for SaaS vs the local steps above:

- **Skip step 1** (no `docker compose up` — the cluster is in Console).
- **Step 3** (`deploy.sh`): export `BASE_URL`, `TOKEN_URL`,
  `ORCHESTRATION_CLIENT_ID`, `ORCHESTRATION_CLIENT_SECRET`,
  `DEFAULT_TENANT_ID` first.
- **Step 4** (workers): Java needs `CAMUNDA_CLIENT_MODE=saas` +
  `CAMUNDA_CLIENT_CLOUD_CLUSTER_ID` + `CAMUNDA_CLIENT_CLOUD_REGION`; Python needs
  `ZEEBE_GRPC_ADDRESS=<cluster-id>.<region>.zeebe.camunda.io:443` and
  **no** `OAUTHLIB_INSECURE_TRANSPORT`.
- **Seed driver**: same `--base-url` / `--token-url` / `--client-id` /
  `--client-secret` overrides as shown above, but pointed at SaaS.
- **Clock control does not work on SaaS** — `PUT /v2/clock` is a
  self-managed-only API, so the seed driver's simulated-past pinning will
  fail against SaaS. Forward-only / live demos work; the backdated
  45-day history that the assessment tool is designed to scan does not.
  If the historical window is the point, stay self-managed.
