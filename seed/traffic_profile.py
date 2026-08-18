"""
Per-process traffic design -- see docs 00_design_proposal.md §5.1 for the
rationale behind each rate (MVP hard-filter targets: P03/P05/P09 tuned to
pass grade B/C + 10-500 starts/day + p95<7d; P01/P13/P15 each tuned to fail
for a distinct, documented reason).

Rates here are DELIBERATELY SCALED DOWN from the design doc's raw daily
targets (which describe production-realistic volume, e.g. P09 at 200/day x
45 days = 9000 instances) to keep a full seed run's wall-clock time and
instance count tractable for a demo/verification estate, while staying
safely inside every relevant threshold (the MVP starts/day filter is
10-500 -- a rate of 15/day clears it exactly as well as 150/day does).
Pass --scale on the CLI to dial this back up for a higher-fidelity run.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional
import os
import random


@dataclass
class ProcessProfile:
    process_id: str
    daily_rate: float  # average instances/day, scaled (see module docstring)
    variables: Callable[[random.Random, int, str], dict]  # (rng, day_index, application_id) -> vars
    directly_startable: bool = True  # has a plain "none" start event
    version: Optional[int] = None  # pin a specific version (fx-settlement v1/v2)
    # <default> for self-managed; override DEFAULT_TENANT_ID for SaaS.
    tenant_id: str = field(default_factory=lambda: os.environ.get("DEFAULT_TENANT_ID", "<default>"))


def _app_id(prefix: str, day: int, seq: int) -> str:
    return f"{prefix}-D{day:+04d}-{seq:03d}"


def loan_application_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {
        "applicationId": app_id,
        "applicants": [{"ref": f"{app_id}-A1"}],
        "requestedAmount": rng.choice([25000, 60000, 150000, 300000, 600000]),
        "underwritingProcessId": "underwriting-review",
        "requiredDocuments": ["passport", "proof-of-address", "payslip"],
    }


def identity_verification_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {
        "applicationId": app_id,
        "applicantRef": f"{app_id}-A1",
        "requiredDocuments": ["passport", "proof-of-address"],
    }


def sanctions_screening_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {"applicantRef": f"{app_id}-A1"}


def credit_bureau_assessment_vars(rng: random.Random, day: int, app_id: str) -> dict:
    amount = rng.choice([25000, 60000, 150000, 300000, 600000])
    return {
        "applicationId": app_id,
        "requestedAmount": amount,
        "monthlyIncome": rng.choice([1800, 2500, 4200, 6000, 9000]),
        "existingDebtRatio": round(rng.uniform(0.1, 0.6), 2),
    }


def document_collection_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {"applicationId": app_id, "requiredDocuments": ["passport", "proof-of-address"]}


def payment_instruction_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {
        "applicationId": app_id,
        "approvedAmount": rng.choice([5000, 15000, 40000, 90000]),
        "currencyPair": rng.choice(["GBP/USD", "GBP/EUR", "USD/EUR"]),
    }


def customer_onboarding_kyc_vars(rng: random.Random, day: int, app_id: str) -> dict:
    n_applicants = rng.choice([1, 1, 2])  # mostly single, some joint
    return {
        "applicationId": app_id,
        "applicants": [{"ref": f"{app_id}-A{i + 1}"} for i in range(n_applicants)],
        "requiredDocuments": ["passport", "proof-of-address"],
    }


def complaint_handling_start_vars(rng: random.Random, day: int, app_id: str) -> dict:
    # Message-start process -- variables travel with the message publish,
    # not a create_instance call. See run_seed.py's complaint driving.
    return {}


def fx_settlement_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {"currencyPair": rng.choice(["GBP/USD", "EUR/USD", "GBP/EUR", "GBP/JPY"])}


def regulatory_reporting_vars(rng: random.Random, day: int, app_id: str) -> dict:
    return {}


# Deliberately scaled per §5.1: P03/P05/P09 comfortably inside [10,500]
# starts/day (MVP candidates); P01 kept low-volume (human/duration-driven,
# not volume-driven -- it's rejected on duration, not starts/day); P13 held
# near its own cron cadence (~1-2/day) specifically to fail the volume
# floor; P15 has zero entry here by design (dormant).
PROFILES: list[ProcessProfile] = [
    ProcessProfile("loan-application", 3, loan_application_vars),
    ProcessProfile("customer-onboarding-kyc", 3, customer_onboarding_kyc_vars),
    ProcessProfile("identity-verification", 15, identity_verification_vars),
    ProcessProfile("sanctions-screening", 2, sanctions_screening_vars),
    ProcessProfile("credit-bureau-assessment", 12, credit_bureau_assessment_vars),
    ProcessProfile("document-collection", 4, document_collection_vars),
    ProcessProfile("payment-instruction", 18, payment_instruction_vars),
    ProcessProfile("fx-settlement", 3, fx_settlement_vars),
    # account-closure: NOT listed -- deliberately dormant, never started.
]

# fx-settlement gets extra direct traffic pinned to v1 and v2 specifically,
# on top of the profile above (which uses latest/v3) -- gap #4, in-flight
# version migration. Rates are small; this is about presence, not volume.
FX_SETTLEMENT_VERSION_PIN = [
    ProcessProfile("fx-settlement", 1.5, fx_settlement_vars, version=1),
    ProcessProfile("fx-settlement", 1.0, fx_settlement_vars, version=2),
]
