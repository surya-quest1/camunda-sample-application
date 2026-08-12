"""P03 identity-verification, P04 sanctions-screening, P05 credit-bureau-assessment."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_p03():
    d = Definitions("Definitions_P03")
    d.error("Error_BureauUnavailable", "BUREAU_UNAVAILABLE", "Identity Bureau Unavailable")
    d.message("Message_SupplementaryEvidence", "SupplementaryEvidenceReceived", correlation_key="=applicantRef")

    p = d.process("identity-verification", "Identity Verification")

    p.start_event("start", "Verification requested")
    p.flow("f1", "start", "svc_check_bureau")

    p.service_task("svc_check_bureau", "Check identity bureau", "check-identity-bureau", retries=3)
    p.flow("f2", "svc_check_bureau", "gw_result")

    # Error boundary: bureau unverifiable -> route to manual review instead of crashing
    p.boundary_event(
        "boundary_bureau_error", "Bureau unverifiable", attached_to="svc_check_bureau",
        kind="error", error_ref="Error_BureauUnavailable",
    )
    p.user_task_zeebe(
        "ut_manual_id_review", "Manual identity review",
        candidate_groups="identity-ops", priority=60,
        form_id="identity-manual-review-form",
    )
    p.flow("f_err1", "boundary_bureau_error", "ut_manual_id_review")
    p.flow("f_err2", "ut_manual_id_review", "call_documents")

    # Non-interrupting message boundary: extra evidence arrives mid-check
    p.boundary_event(
        "boundary_extra_evidence", "Extra evidence arrives", attached_to="svc_check_bureau",
        kind="message", cancel_activity=False,
        message_ref="Message_SupplementaryEvidence",
    )
    p.service_task("svc_record_evidence", "Record supplementary evidence", "record-supplementary-evidence")
    p.flow("f_ne1", "boundary_extra_evidence", "svc_record_evidence")
    p.end_event("end_evidence_recorded", "Evidence recorded")
    p.flow("f_ne2", "svc_record_evidence", "end_evidence_recorded")

    p.gateway("gw_result", "Verified?", "exclusive", default="f_unverified")
    p.call_activity(
        "call_documents", "Collect ID documents", "document-collection",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicantRef": "applicantRef", "=requiredDocuments": "requiredDocuments"},
    )
    p.flow("f_verified", "gw_result", "call_documents", condition="=bureauStatus = \"verified\"", name="Verified")
    p.flow("f_unverified", "gw_result", "ut_manual_id_review", name="Unverified")

    p.end_event("end", "Verification complete")
    p.flow("f3", "call_documents", "end")

    return d


def build_p04():
    d = Definitions("Definitions_P04")

    p = d.process("sanctions-screening", "Sanctions Screening")

    p.start_event("start", "Screening requested")
    p.flow("f1", "start", "svc_screen")

    p.service_task("svc_screen", "Screen against sanctions/PEP lists", "screen-sanctions-pep", retries=3)
    p.flow("f2", "svc_screen", "end")

    # Signal catch: re-screen everyone in flight when the sanctions list changes
    p.intermediate_catch_event(
        "catch_list_updated", "Sanctions list updated", kind="signal",
        signal_ref=d.signal("Signal_SanctionsListUpdated", "SanctionsListUpdated"),
    )
    p.flow("f3", "catch_list_updated", "svc_rescreen")
    p.service_task("svc_rescreen", "Re-screen applicant", "rescreen-sanctions-pep", retries=3)
    p.flow("f4", "svc_rescreen", "end")

    # Unbounded cycle timer: re-screen every 6 hours, forever, no repeat
    # limit. Modelled as a SECOND start event, not an intermediate catch --
    # Zeebe only allows timeCycle on a start event; an intermediate/boundary
    # timer catch must be timeDate or timeDuration (one-shot). A process may
    # have multiple start events as long as at most one is a plain "none"
    # start, which this doesn't conflict with.
    p.start_event(
        "timer_periodic_rescreen", "Every 6 hours", kind="timer",
        timer_type="timeCycle", value="R/PT6H",
    )
    p.flow("f5", "timer_periodic_rescreen", "svc_rescreen")

    p.end_event("end", "Screening complete")

    return d


def build_p05():
    d = Definitions("Definitions_P05")
    d.escalation("Escalation_SeniorReview", "SENIOR_ANALYST_REVIEW", "Senior Analyst Review")

    p = d.process("credit-bureau-assessment", "Credit Bureau Assessment")

    p.start_event("start", "Assessment requested")
    p.flow("f1", "start", "svc_pull_report")

    # REST outbound connector -- config-driven, not a job worker per se, but
    # deploys as a service task whose job type the connector runtime polls.
    # Config goes via zeebe:ioMapping input variables (method, url), NOT
    # taskHeaders -- confirmed live: the http-json connector's own input
    # validation rejected taskHeaders-supplied method/url as null, since it
    # reads them as FEEL-evaluated input variables like any other connector
    # property, not static task metadata.
    p.service_task(
        "svc_pull_report", "Pull credit bureau report", "io.camunda:http-json:1",
        io_in={"=\"POST\"": "method", "=\"https://credit-bureau.internal.example.com/v1/reports\"": "url"},
        modeler_template="io.camunda.connectors.HttpJson.v2",
    )
    p.flow("f2", "svc_pull_report", "svc_core_banking")

    # Custom element template calling the internal Core Banking API, with a
    # connector secret reference.
    p.service_task(
        "svc_core_banking", "Post to Core Banking API", "core-banking-api-call",
        headers={"authToken": "{{secrets.CORE_BANKING_TOKEN}}"},
        modeler_template="com.northwindbank.connectors.CoreBankingApi.v1",
    )
    p.flow("f3", "svc_core_banking", "sub_credit_evaluation")

    # In-broker DMN business rule task, wrapped in an embedded subprocess --
    # an escalation boundary event can only attach to a subprocess or call
    # activity, not a plain task (Zeebe's deploy validator), so the
    # non-interrupting boundary below needs this wrapper regardless.
    sub = p.sub_process("sub_credit_evaluation", "Credit risk evaluation")
    sub.start_event("sub_start", "Evaluation started")
    sub.flow("sf1", "sub_start", "br_credit_risk")
    sub.business_rule_task_in_broker(
        "br_credit_risk", "Evaluate credit risk", decision_id="affordability-band",
        result_variable="affordabilityBand", binding_type="latest",
    )
    sub.flow("sf2", "br_credit_risk", "sub_end")
    sub.end_event("sub_end", "Evaluation complete")
    p.flow("f4", "sub_credit_evaluation", "gw_high_value")

    p.gateway("gw_high_value", "High value?", "exclusive", default="f_standard")
    p.flow("f_high_value", "gw_high_value", "esc_senior_review",
           condition="=requestedAmount > 250000", name="High value")
    p.flow("f_standard", "gw_high_value", "catch_rate_change", name="Standard")

    # Non-interrupting boundary escalation on the evaluation subprocess: if
    # a senior-review flag is raised mid-evaluation, notify a senior analyst
    # in parallel WITHOUT stopping the assessment -- escalation.nonInterrupting.
    p.boundary_event(
        "boundary_senior_flag", "Senior review flag raised", attached_to="sub_credit_evaluation",
        kind="escalation", cancel_activity=False, escalation_ref="Escalation_SeniorReview",
    )
    p.service_task("svc_notify_senior_analyst", "Notify senior analyst", "notify-senior-analyst")
    p.flow("f_ne_esc1", "boundary_senior_flag", "svc_notify_senior_analyst")
    p.end_event("end_senior_notified", "Senior analyst notified")
    p.flow("f_ne_esc2", "svc_notify_senior_analyst", "end_senior_notified")

    # Interrupting escalation throw (high-value path): refers the case up
    # and stops further automated processing here -- escalation.interrupting.
    p.intermediate_throw_event(
        "esc_senior_review", "Escalate to senior analyst", kind="escalation",
        escalation_ref="Escalation_SeniorReview",
    )
    p.flow("f5", "esc_senior_review", "catch_rate_change")

    # Signal catch: base-rate change affects affordability
    p.intermediate_catch_event(
        "catch_rate_change", "Base rate changed", kind="signal",
        signal_ref="Signal_BaseRateChanged",
    )
    d.signal("Signal_BaseRateChanged", "BaseRateChanged")
    p.flow("f6", "catch_rate_change", "end")

    p.end_event("end", "Assessment complete")

    return d


if __name__ == "__main__":
    for name, builder in [
        ("identity-verification", build_p03),
        ("sanctions-screening", build_p04),
        ("credit-bureau-assessment", build_p05),
    ]:
        out = builder().tostring()
        path = f"models/{name}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
