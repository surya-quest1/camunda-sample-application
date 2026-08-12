# Two-pool spike: result

Ran 2026-08-12 against the local Camunda 8.8 cluster (`cluster/docker-compose-full.yaml`).
Source: `models/two-pool-spike.bpmn` (generator: `scripts/gen_fixtures.py`).

## Question

Can `gateway.complex` and `conditionalEvent` (F01/F02 -- constructs Zeebe cannot
*execute*) still get *static inventory* coverage, by modelling them in a
non-executable second pool alongside a deployable executable pool in the same
file?

## Result: yes, on both counts

**1. Deploy succeeds.** `POST /v2/deployments` with a file containing one
`isExecutable="true"` process and one `isExecutable="false"` process, wired
into a `<bpmn:collaboration>`, returns `200` and registers only the
executable process as a process definition:

```json
{"tenantId":"<default>","deploymentKey":"2251799813685863","deployments":[
  {"processDefinition":{"processDefinitionId":"two-pool-spike-executable", ...}}
]}
```

No rejection, no validation error on the non-executable pool's complex
gateway or conditional event -- Zeebe's deploy validator only checks the
executable process.

**2. The full resource is served back on read.** `GET /v2/process-definitions/{key}/xml`
-- the exact call `pkg/collectors/bpmnxml.go`'s `FetchProcessDefinitionXML`
already makes -- returns the *entire* deployed file, both pools intact. See
`two-pool-spike-fetched-from-cluster.bpmn` in this directory: the complex
gateway (`na_gw`) and conditional event (`na_catch`) are both present,
byte-identical to what was deployed.

## But today's analyser still misses both

Running the real `bpmnanalyser.Parse` (via `scripts/bpmn-validate`) against
the fetched XML:

```
Parse() picked processId: two-pool-spike-executable
Gateways found: None
ConditionalEvents found: None
```

Confirms the gap named in `pkg/bpmnanalyser/parse.go`'s own doc comment --
*"If the document defines more than one `<bpmn:process>`, only the first is
parsed"* -- concretely: the data is sitting in the same XML string the tool
already has in hand, and it's discarded, not because it can't be reached,
but because `Parse()` only ever looks at the first `<bpmn:process>` element
in document order.

## What this confirms

The fix proposed is now empirically validated, not just theoretical:

- Select the process to parse **by matching `id` against the definition
  being processed** (the caller already knows which `processDefinitionId`
  it asked for), instead of taking the first `<bpmn:process>`.
- Optionally, walk sibling non-executable pools too and report their
  elements as *modelled-but-never-executable* -- distinct from the primary
  census, since they were never deployable as running processes.

This is a real, reproducible, low-risk fix: it doesn't require a new
Connector call, a new collector, or any change to what data reaches the
tool -- only which part of data already in hand gets read.
