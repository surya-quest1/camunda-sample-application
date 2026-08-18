#!/usr/bin/env python3
"""
Targeted top-up reseed for the 3 processes whose BPMN/worker fixes were
applied AFTER the main 45-day run: credit-bureau-assessment (connector
config fix), payment-instruction (added gateway), fx-settlement (worker
now leaves a fraction of jobs deliberately unresolved so old versions keep
live instances). Existing instances from before the fix are unaffected --
this only adds fresh instances against the now-fixed process definitions.

Reuses ClockController/ApiClient exactly like run_seed.py, over a shorter
7-day window -- enough to populate the assessment tool's runtime window.
"""
import argparse
import os
import random
import sys
import time

from api_client import ApiClient
from clock import ClockController, wait_for_clock_settle


def log(msg: str) -> None:
    print(f"[reseed] {msg}", file=sys.stderr, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.environ.get("ZEEBE_REST_ADDRESS", "http://localhost:8088"))
    p.add_argument("--token-url", default=os.environ.get("CAMUNDA_OAUTH_URL", "http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token"))
    p.add_argument("--client-id", default=os.environ.get("CAMUNDA_CLIENT_ID", "orchestration"))
    p.add_argument("--client-secret", default=os.environ.get("CAMUNDA_CLIENT_SECRET", "secret"))
    p.add_argument("--audience", default=os.environ.get("CAMUNDA_TOKEN_AUDIENCE"))
    args = p.parse_args()

    rng = random.Random(43)
    client = ApiClient(args.base_url, args.token_url, args.client_id, args.client_secret,
                       audience=args.audience)
    clock = ClockController(args.base_url, client.token)

    try:
        for day in range(-7, 1):
            log(f"day {day:+d} / 0 ...")
            clock.pin_days_ago(-day)
            wait_for_clock_settle()

            # credit-bureau-assessment -- now fixed connector config
            for _ in range(rng.randint(10, 16)):
                amount = rng.choice([25000, 60000, 150000, 300000])
                client.create_instance("credit-bureau-assessment", {
                    "applicationId": f"CBA-FIX-D{day:+04d}-{rng.randint(1000,9999)}",
                    "requestedAmount": amount,
                    "monthlyIncome": rng.choice([1800, 2500, 4200, 6000, 9000]),
                    "existingDebtRatio": round(rng.uniform(0.1, 0.6), 2),
                })

            # payment-instruction -- now has a gateway construct
            for _ in range(rng.randint(12, 20)):
                client.create_instance("payment-instruction", {
                    "applicationId": f"PAY-FIX-D{day:+04d}-{rng.randint(1000,9999)}",
                    "approvedAmount": rng.choice([5000, 15000, 40000, 90000, 60000]),
                    "currencyPair": rng.choice(["GBP/USD", "GBP/EUR", "USD/EUR"]),
                })

            # fx-settlement -- pinned to v1 and v2 specifically, so both
            # old versions get fresh instances (a fifth of which the
            # worker now leaves permanently active).
            for version in (1, 2):
                for _ in range(rng.randint(2, 4)):
                    client.create_instance("fx-settlement", {
                        "currencyPair": rng.choice(["GBP/USD", "EUR/USD", "GBP/EUR"]),
                    }, version=version)

            time.sleep(0.3)

        log("done. waiting 10s for workers to drain the final day's jobs...")
        time.sleep(10)

    finally:
        log("resetting clock to real time...")
        clock.reset()
        log("clock reset.")


if __name__ == "__main__":
    main()
