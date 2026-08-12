# Clock-control spike: result

Ran 2026-08-12 against the local Camunda 8.8.34 cluster.

## Question

Doc 00 §6.1 identified the clock-control mechanism (`PUT /v2/clock`,
`POST /v2/clock/reset`) as the highest-risk unknown in the whole seeding
plan. Does pinning the clock actually backdate the timestamps Zeebe stamps
into instance records — the entire premise the 45-day history plan depends
on?

## Result: confirmed, exactly as designed

```
>>> clock.pin_days_ago(10)
pinned clock to 2026-08-02 08:19:11.950174+00:00

>>> client.create_instance('loan-application', {...})
created instance: {'processInstanceKey': '2251799813685517', ...}
```

Querying the instance back via `POST /v2/process-instances/search`:

```json
{
  "processInstanceKey": "2251799813685517",
  "startDate": "2026-08-02T08:19:11.950Z",
  "state": "ACTIVE"
}
```

`startDate` is exactly the pinned timestamp, not the real wall-clock time —
confirmed end to end: pin → create instance → the Camunda exporter → the
searchable index. This is the mechanism `seed/clock.py` (`ClockController`)
wraps, and it is what the simulated-time seeding loop in
`00_design_proposal.md §6.1` depends on.

## Mechanics confirmed empirically

- `PUT /v2/clock` with `{"timestamp": <epoch-ms>}` pins to an exact instant
  (no auto-advance) -- matches the OpenAPI spec's own description.
  `POST /v2/clock/reset` returns to real time.
- No special enablement was needed on this cluster -- the endpoint worked
  immediately once the OIDC token had `SYSTEM UPDATE` permission (the
  `orchestration` client's default admin role already covers it).
- A short settle delay (`wait_for_clock_settle`, ~1s) avoids racing a pin
  against a still-in-flight instance-creation call, observed empirically
  rather than documented anywhere.

## Not yet exercised by this spike

- Whether re-pinning forward by a day reliably fires a `P1D`-scale timer
  (expected to work, per the API's own semantics, but not yet observed).
- Retention/ILM behaviour on 10+-day-old backdated records (the other
  named risk in the design doc) -- still open, see task
  "Disable retention and ILM then verify".
