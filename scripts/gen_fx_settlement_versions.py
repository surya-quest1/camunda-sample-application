"""
P16 fx-settlement needs to exist at v1/v2/v3 on the cluster, with live
instances left running on v1 and v2 while v3 is latest -- the in-flight
migration constraint (doc 06 gap #4). Zeebe only creates a new version on a
deploy whose resource content actually differs (it dedupes identical bytes),
so v2/v3 need genuine content changes, not just redeploys of the same file.

This script writes fx-settlement.bpmn (v1, already the base file from
gen_p13_p14_p15_p16.py) plus two content-distinct variants for the deploy
script to submit in order.
"""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_v2():
    """v2 adds a settlement-confirmation step -- same processId, real
    structural change."""
    d = Definitions("Definitions_P16_v2")
    p = d.process("fx-settlement", "FX Settlement")

    p.start_event("start", "Settlement requested")
    p.flow("f1", "start", "svc_lock_rate")
    p.service_task("svc_lock_rate", "Lock FX rate", "lock-fx-rate", retries=3)
    p.flow("f2", "svc_lock_rate", "svc_settle")
    p.service_task("svc_settle", "Settle currency leg", "settle-fx-leg", retries=3)
    p.flow("f3", "svc_settle", "svc_confirm")
    # v2 addition:
    p.service_task("svc_confirm", "Confirm settlement", "confirm-fx-settlement", retries=2)
    p.flow("f4", "svc_confirm", "end")
    p.end_event("end", "Settlement complete")
    return d


def build_v3():
    """v3 adds a reconciliation step on top of v2 -- the version deployed
    last, hence 'latest', while v1/v2 instances are still in flight."""
    d = Definitions("Definitions_P16_v3")
    p = d.process("fx-settlement", "FX Settlement")

    p.start_event("start", "Settlement requested")
    p.flow("f1", "start", "svc_lock_rate")
    p.service_task("svc_lock_rate", "Lock FX rate", "lock-fx-rate", retries=3)
    p.flow("f2", "svc_lock_rate", "svc_settle")
    p.service_task("svc_settle", "Settle currency leg", "settle-fx-leg", retries=3)
    p.flow("f3", "svc_settle", "svc_confirm")
    p.service_task("svc_confirm", "Confirm settlement", "confirm-fx-settlement", retries=2)
    p.flow("f4", "svc_confirm", "svc_reconcile")
    # v3 addition:
    p.service_task("svc_reconcile", "Reconcile against ledger", "reconcile-fx-ledger", retries=2)
    p.flow("f5", "svc_reconcile", "end")
    p.end_event("end", "Settlement complete")
    return d


if __name__ == "__main__":
    for suffix, builder in [("v2", build_v2), ("v3", build_v3)]:
        out = builder().tostring()
        path = f"models/fx-settlement-{suffix}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
