"""P01 loan-application -- the root orchestrator. See docs/02_application_walkthrough.md."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build():
    d = Definitions("Definitions_P01")

    d.message("Message_ApplicationCancelled", "ApplicationCancelled", correlation_key="=applicationId")
    d.error("Error_UnderwritingDeclined", "UNDERWRITING_DECLINED", "Underwriting Declined")

    p = d.process("loan-application", "Loan Application")

    p.start_event("start", "Application submitted")
    p.flow("f_start_parallel", "start", "gw_split")

    p.gateway("gw_split", "Split onboarding / credit", "parallel")

    # Branch 1: onboarding (P02)
    p.call_activity(
        "call_onboarding", "Onboard & verify KYC", "customer-onboarding-kyc",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId", "=applicants": "applicants"},
        io_out={"=kycOutcome": "kycOutcome"},
    )
    p.flow("f_split_onboarding", "gw_split", "call_onboarding")

    # Branch 2: credit assessment (P05)
    p.call_activity(
        "call_credit", "Assess credit bureau", "credit-bureau-assessment",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId"},
        io_out={"=affordabilityBand": "affordabilityBand"},
    )
    p.flow("f_split_credit", "gw_split", "call_credit")

    p.gateway("gw_join", "Join onboarding / credit", "parallel")
    p.flow("f_onboarding_join", "call_onboarding", "gw_join")
    p.flow("f_credit_join", "call_credit", "gw_join")

    # Documents (P06 -- shared child, also called by P03 and P10)
    p.call_activity(
        "call_documents", "Collect documents", "document-collection",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId", "=requiredDocuments": "requiredDocuments"},
        io_out={"=documentsComplete": "documentsComplete"},
    )
    p.flow("f_join_documents", "gw_join", "call_documents")

    # Underwriting (P07 -- DYNAMIC call, FEEL expression target -- deliberately unresolvable statically)
    p.call_activity(
        "call_underwriting", "Underwriting review", "=underwritingProcessId",
        propagate_parent=True, propagate_child=False,
        io_in={"=applicationId": "applicationId", "=affordabilityBand": "affordabilityBand"},
        io_out={"=underwritingDecision": "underwritingDecision"},
    )
    p.flow("f_documents_underwriting", "call_documents", "call_underwriting")

    p.gateway("gw_decision", "Decision", "exclusive", default="f_decision_decline")
    p.flow("f_underwriting_decision", "call_underwriting", "gw_decision")

    # Approve path -> disbursement (P08)
    p.call_activity(
        "call_disbursement", "Disburse funds", "fund-disbursement",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId", "=approvedAmount": "approvedAmount"},
    )
    p.flow("f_decision_approve", "gw_decision", "call_disbursement",
           condition="=underwritingDecision = \"approved\"", name="Approved")
    p.end_event("end_funded", "Funded")
    p.flow("f_disbursement_end", "call_disbursement", "end_funded")

    # Refer path -> loop back to underwriting for more info
    p.flow("f_decision_refer", "gw_decision", "call_underwriting",
           condition="=underwritingDecision = \"referred\"", name="Referred")

    # Decline path (default) -> terminate
    p.end_event("end_declined", "Declined", kind="terminate")
    p.flow("f_decision_decline", "gw_decision", "end_declined")

    # --- Interrupting event subprocess: client withdraws at any point ---
    esp = p.sub_process("event_withdrawal", "Client withdraws", triggered_by_event=True)
    esp.start_event("start_withdrawal", "Withdrawal requested", kind="message",
                     message_ref=d.message("Message_WithdrawalRequested", "WithdrawalRequested",
                                            correlation_key="=applicationId"))
    esp.service_task("svc_process_withdrawal", "Process withdrawal", "process-withdrawal")
    esp.flow("f_w1", "start_withdrawal", "svc_process_withdrawal")
    esp.end_event("end_withdrawal", "Withdrawn", kind="terminate")
    esp.flow("f_w2", "svc_process_withdrawal", "end_withdrawal")

    # --- Interrupting message boundary event: client cancels ---
    p.boundary_event(
        "boundary_cancel", "Client cancels", attached_to="call_underwriting",
        kind="message", cancel_activity=True,
        message_ref="Message_ApplicationCancelled",
    )
    p.service_task("svc_process_cancellation", "Process cancellation", "process-cancellation")
    p.flow("f_cancel1", "boundary_cancel", "svc_process_cancellation")
    p.end_event("end_cancelled", "Cancelled", kind="terminate")
    p.flow("f_cancel2", "svc_process_cancellation", "end_cancelled")

    return d


if __name__ == "__main__":
    out = build().tostring()
    with open("models/loan-application.bpmn", "w") as f:
        f.write(out)
    print("wrote models/loan-application.bpmn")
