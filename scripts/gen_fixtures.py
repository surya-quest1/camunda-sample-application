"""
F01/F02 -- constructs the engine cannot execute (complex gateway, conditional
event). Two files:

  1. fixtures/complex-gateway.bpmn, fixtures/conditional-event.bpmn --
     single-pool, non-executable (isExecutable="false") standalone files.
     These can NEVER be deployed to Zeebe (executable="false" is rejected by
     the deploy validator) -- unit-fixture-only, mirrored into
     assessment-tool/pkg/bpmnanalyser/testdata/ by hand (not by this script;
     see docs/00_design_proposal.md).

  2. models/two-pool-spike.bpmn -- the actual spike artifact: ONE executable
     process (deployable) plus a SECOND, non-executable pool in the same
     file carrying the two undeployable constructs, wired into a
     <bpmn:collaboration>. Tests whether Zeebe (a) accepts the deploy at
     all with a mixed collaboration, and (b) serves back the full resource
     XML including the non-executable pool on GET -- see
     docs/02_application_walkthrough.md §7.
"""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_fixture_complex_gateway():
    d = Definitions("Definitions_F01")
    p = d.process("complex-gateway-fixture", "Complex Gateway Fixture", executable=False)
    p.start_event("start", "Start")
    p.flow("f1", "start", "gw_complex")
    p.gateway("gw_complex", "Complex routing", "complex")
    p.service_task("svc_a", "Branch A", "branch-a")
    p.service_task("svc_b", "Branch B", "branch-b")
    p.flow("f2", "gw_complex", "svc_a")
    p.flow("f3", "gw_complex", "svc_b")
    p.end_event("end_a", "End A")
    p.end_event("end_b", "End B")
    p.flow("f4", "svc_a", "end_a")
    p.flow("f5", "svc_b", "end_b")
    return d


def build_fixture_conditional_event():
    d = Definitions("Definitions_F02")
    p = d.process("conditional-event-fixture", "Conditional Event Fixture", executable=False)
    p.start_event("start", "Start")
    p.flow("f1", "start", "svc_a")
    p.service_task("svc_a", "Do work", "do-work")
    p.flow("f2", "svc_a", "catch_condition")
    p.intermediate_catch_event(
        "catch_condition", "Balance threshold reached", kind="conditional",
        condition="=accountBalance > 10000",
    )
    p.flow("f3", "catch_condition", "end")
    p.end_event("end", "End")
    return d


def build_two_pool_spike():
    """The actual deploy spike: one executable pool + one non-executable
    pool carrying the two undeployable constructs, in a single file."""
    d = Definitions("Definitions_TwoPoolSpike")

    executable = d.process("two-pool-spike-executable", "Two-Pool Spike (Executable)", executable=True)
    executable.start_event("start", "Start")
    executable.flow("f1", "start", "svc")
    executable.service_task("svc", "Do work", "spike-do-work")
    executable.flow("f2", "svc", "end")
    executable.end_event("end", "End")

    non_executable = d.process("two-pool-spike-analyst-pool", "Analyst Pool (non-executable)", executable=False)
    non_executable.start_event("na_start", "Start")
    non_executable.flow("naf1", "na_start", "na_gw")
    non_executable.gateway("na_gw", "Complex routing", "complex")
    non_executable.service_task("na_svc", "Branch", "branch-na")
    non_executable.flow("naf2", "na_gw", "na_svc")
    non_executable.flow("naf3", "na_svc", "na_catch")
    non_executable.intermediate_catch_event(
        "na_catch", "Balance threshold reached", kind="conditional",
        condition="=accountBalance > 10000",
    )
    non_executable.flow("naf4", "na_catch", "na_end")
    non_executable.end_event("na_end", "End")

    d.collaboration("Collaboration_TwoPoolSpike", [
        ("two-pool-spike-executable", "Northwind Processing"),
        ("two-pool-spike-analyst-pool", "Business Analyst Sketch"),
    ])

    return d


if __name__ == "__main__":
    out = build_fixture_complex_gateway().tostring()
    with open("fixtures/complex-gateway.bpmn", "w") as f:
        f.write(out)
    print("wrote fixtures/complex-gateway.bpmn")

    out = build_fixture_conditional_event().tostring()
    with open("fixtures/conditional-event.bpmn", "w") as f:
        f.write(out)
    print("wrote fixtures/conditional-event.bpmn")

    out = build_two_pool_spike().tostring()
    with open("models/two-pool-spike.bpmn", "w") as f:
        f.write(out)
    print("wrote models/two-pool-spike.bpmn")
