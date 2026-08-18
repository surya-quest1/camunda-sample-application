#!/usr/bin/env python3
"""
Reproducible history-seeding driver for the Northwind Private Bank estate.

Re-runnable against ANY cluster with this estate deployed -- all connection
details are parameters (CLI flags / env vars), nothing is hardcoded to this
machine. Given the same --seed, the *shape* of the traffic (which processes,
how many instances per simulated day, which branches/outcomes) is
deterministic; exact instance keys and real-world wall-clock timestamps of
course differ run to run.

Mechanism (see docs/spike-results/clock-control-RESULTS.md): steps the
Zeebe broker's engine clock backwards via PUT /v2/clock, one simulated day
at a time, starting that day's cohort of instances before advancing --
letting each day's timers get a chance to fire as the clock steps through
their due dates. See 00_design_proposal.md §6 for the full design; this
implementation deliberately scales daily instance counts down from that
doc's production-realistic targets to keep a full run's wall-clock time
tractable -- see traffic_profile.py's docstring.

Usage:
    python3 seed/run_seed.py [--days 45] [--scale 1.0] [--seed 42]
                              [--base-url http://localhost:8088]
                              [--token-url http://localhost:18080/...]
                              [--client-id orchestration] [--client-secret secret]
                              [--dry-run]

Safe to interrupt (Ctrl-C) -- resets the clock to real time in a finally
block regardless of how far the loop got.
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

from api_client import ApiClient
from clock import ClockController, wait_for_clock_settle
from traffic_profile import PROFILES, FX_SETTLEMENT_VERSION_PIN, _app_id

# ---------------------------------------------------------------------------
# Leave-behind state design (00_design_proposal.md §5.4) -- completion /
# publish probabilities tuned so a realistic FRACTION of instances resolve
# and the rest are left genuinely parked (tasks, message waits, incidents),
# not because of a bug.
# ---------------------------------------------------------------------------
USER_TASK_COMPLETION_PROBABILITY = 0.55
DOCUMENT_MESSAGE_PUBLISH_PROBABILITY = 0.6
CLIENT_RESPONSE_PUBLISH_PROBABILITY = 0.5
LONG_RUNNING_INSTANCE_EXTRA_DAYS = 15  # on top of --days -> ~60 total, per design

USER_TASK_VARIABLES = {
    "ut_first_review": lambda rng: {"underwritingDecision": rng.choices(
        ["approved", "referred", "declined"], weights=[0.55, 0.25, 0.2])[0]},
    "ut_second_review": lambda rng: {"secondSignoffDecision": rng.choices(
        ["confirmed", "overruled"], weights=[0.8, 0.2])[0]},
    "ut_manual_id_review": lambda rng: {"manualVerificationOutcome": rng.choices(
        ["verified", "rejected"], weights=[0.75, 0.25])[0]},
    "ut_manual_upload": lambda rng: {"documentType": "passport", "documentRef": f"DOC-{rng.randint(1000, 9999)}"},
    "ut_triage": lambda rng: {
        "isRegulatoryBreach": rng.random() < 0.15,
        "severity": rng.choices(["low", "standard", "high"], weights=[0.4, 0.45, 0.15])[0],
    },
}


def log(msg: str) -> None:
    print(f"[seed] {msg}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, default=45, help="how many simulated days of history to produce")
    p.add_argument("--scale", type=float, default=1.0, help="multiplier on traffic_profile.py's daily rates")
    p.add_argument("--seed", type=int, default=42, help="RNG seed -- fixes the shape of the run, not exact keys")
    p.add_argument("--base-url", default=os.environ.get("ZEEBE_REST_ADDRESS", "http://localhost:8088"))
    p.add_argument("--token-url", default=os.environ.get("CAMUNDA_OAUTH_URL", "http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token"))
    p.add_argument("--client-id", default=os.environ.get("CAMUNDA_CLIENT_ID", "orchestration"))
    p.add_argument("--client-secret", default=os.environ.get("CAMUNDA_CLIENT_SECRET", "secret"))
    p.add_argument("--audience", default=os.environ.get("CAMUNDA_TOKEN_AUDIENCE"))
    p.add_argument("--dry-run", action="store_true", help="print the plan without calling the cluster")
    return p.parse_args()


def poisson(rng: random.Random, mean: float) -> int:
    """Knuth's algorithm -- avoids a numpy dependency for one distribution."""
    if mean <= 0:
        return 0
    l = pow(2.718281828459045, -mean)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1


def seed_day_cohort(client: ApiClient, rng: random.Random, day: int, scale: float,
                     pending_documents: list, pending_client_responses: list, dry_run: bool) -> int:
    created = 0
    for profile in PROFILES:
        if not profile.directly_startable:
            continue
        count = poisson(rng, profile.daily_rate * scale)
        for seq in range(count):
            app_id = _app_id(profile.process_id.split("-")[0].upper(), day, seq)
            variables = profile.variables(rng, day, app_id)
            if dry_run:
                created += 1
                continue
            try:
                client.create_instance(profile.process_id, variables, tenant_id=profile.tenant_id,
                                        version=profile.version)
                created += 1
                if profile.process_id in ("document-collection", "identity-verification"):
                    pending_documents.append(app_id)
                if profile.process_id == "loan-application":
                    pending_client_responses.append(app_id)
            except RuntimeError as e:
                log(f"  WARN create {profile.process_id} failed: {e}")

    for profile in FX_SETTLEMENT_VERSION_PIN:
        count = poisson(rng, profile.daily_rate * scale)
        for seq in range(count):
            app_id = _app_id("FXV" + str(profile.version), day, seq)
            if dry_run:
                created += 1
                continue
            try:
                client.create_instance(profile.process_id, profile.variables(rng, day, app_id),
                                        version=profile.version)
                created += 1
            except RuntimeError as e:
                log(f"  WARN create fx-settlement v{profile.version} failed: {e}")
    return created


def drive_signals_and_messages(client: ApiClient, rng: random.Random, day: int,
                                pending_documents: list, pending_client_responses: list,
                                dry_run: bool) -> None:
    if dry_run:
        return

    # Base-rate change broadcast: roughly every 6 simulated days.
    if day % 6 == 0:
        try:
            client.broadcast_signal("BaseRateChanged", {"newRate": round(rng.uniform(3.5, 6.5), 2)})
        except RuntimeError as e:
            log(f"  WARN signal BaseRateChanged failed: {e}")

    # Sanctions list update: roughly every 4 simulated days.
    if day % 4 == 0:
        try:
            client.broadcast_signal("SanctionsListUpdated")
        except RuntimeError as e:
            log(f"  WARN signal SanctionsListUpdated failed: {e}")

    # Complaint arrivals: message-start process, published directly.
    if rng.random() < 0.3:
        complaint_id = f"COMPLAINT-D{day:+04d}-{rng.randint(100, 999)}"
        try:
            client.publish_message("ComplaintReceived", complaint_id, {
                "complaintId": complaint_id,
                "complaintSummary": rng.choice([
                    "Delay in fund disbursement", "Incorrect fee charged",
                    "Unable to reach relationship manager", "Statement discrepancy",
                ]),
            })
        except RuntimeError as e:
            log(f"  WARN complaint publish failed: {e}")

    # Resolve a fraction of pending document confirmations and client
    # responses -- the rest stay genuinely parked (leave-behind state).
    still_pending_docs = []
    for app_id in pending_documents:
        if rng.random() < DOCUMENT_MESSAGE_PUBLISH_PROBABILITY:
            try:
                client.publish_message("DocumentReceived", app_id)
                client.publish_message("CollectionConfirmed", app_id)
            except RuntimeError:
                still_pending_docs.append(app_id)
        else:
            still_pending_docs.append(app_id)
    pending_documents[:] = still_pending_docs[-500:]  # bound memory on long runs

    still_pending_resp = []
    for app_id in pending_client_responses:
        if rng.random() < CLIENT_RESPONSE_PUBLISH_PROBABILITY:
            try:
                client.publish_message("ClientResponded", app_id)
            except RuntimeError:
                still_pending_resp.append(app_id)
        else:
            still_pending_resp.append(app_id)
    pending_client_responses[:] = still_pending_resp[-500:]


def complete_some_user_tasks(client: ApiClient, rng: random.Random, dry_run: bool) -> int:
    if dry_run:
        return 0
    completed = 0
    try:
        tasks = client.search_user_tasks(state="CREATED", page_limit=50)
    except RuntimeError as e:
        log(f"  WARN task search failed: {e}")
        return 0
    for task in tasks:
        if rng.random() >= USER_TASK_COMPLETION_PROBABILITY:
            continue  # left parked -- the leave-behind state design wants this
        element_id = task.get("elementId", "")
        var_fn = USER_TASK_VARIABLES.get(element_id)
        variables = var_fn(rng) if var_fn else {}
        try:
            client.complete_user_task(task["userTaskKey"], variables)
            completed += 1
        except RuntimeError as e:
            log(f"  WARN complete task {element_id} failed: {e}")
    return completed


def seed_long_running_instance(client: ApiClient, clock: ClockController, rng: random.Random,
                                days: int, dry_run: bool) -> None:
    """One loan-application instance started well before the main window and
    deliberately never advanced past its underwriting wait -- the
    longestRunningInstanceDays design element."""
    total_days_ago = days + LONG_RUNNING_INSTANCE_EXTRA_DAYS
    log(f"seeding the long-running instance at day -{total_days_ago}...")
    if dry_run:
        return
    clock.pin_days_ago(total_days_ago)
    wait_for_clock_settle()
    app_id = "APP-LONGRUNNING-001"
    client.create_instance("loan-application", {
        "applicationId": app_id,
        "applicants": [{"ref": f"{app_id}-A1"}],
        "requestedAmount": 450000,
        "underwritingProcessId": "underwriting-review",
        "requiredDocuments": ["passport", "proof-of-address", "payslip"],
    })
    # Deliberately no ClientResponded publish for this one -- it stays
    # parked at underwriting indefinitely, which is the point.


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    client = ApiClient(args.base_url, args.token_url, args.client_id, args.client_secret,
                       audience=args.audience)
    clock = ClockController(args.base_url, client.token)

    pending_documents: list = []
    pending_client_responses: list = []
    total_created = 0

    try:
        seed_long_running_instance(client, clock, rng, args.days, args.dry_run)

        for day in range(-args.days, 1):
            log(f"day {day:+d} / 0  (pinning clock)...")
            if not args.dry_run:
                clock.pin_days_ago(-day)
                wait_for_clock_settle()

            created = seed_day_cohort(client, rng, day, args.scale, pending_documents,
                                       pending_client_responses, args.dry_run)
            drive_signals_and_messages(client, rng, day, pending_documents,
                                        pending_client_responses, args.dry_run)
            completed = complete_some_user_tasks(client, rng, args.dry_run)

            total_created += created
            log(f"  created {created} instances, completed {completed} user tasks, "
                f"pending_docs={len(pending_documents)} pending_responses={len(pending_client_responses)}")

            if not args.dry_run:
                time.sleep(0.3)  # let workers drain the day's jobs before advancing

        log(f"done. {total_created} instances created across {args.days + 1} simulated days "
            f"(+ 1 long-running seed at day -{args.days + LONG_RUNNING_INSTANCE_EXTRA_DAYS}).")

    finally:
        if not args.dry_run:
            log("resetting clock to real time...")
            clock.reset()
            log("clock reset.")


if __name__ == "__main__":
    main()
