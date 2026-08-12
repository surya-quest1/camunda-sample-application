"""P08 fund-disbursement (compensation saga), P09 payment-instruction."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_p08():
    d = Definitions("Definitions_P08")

    p = d.process("fund-disbursement", "Fund Disbursement")

    p.start_event("start", "Disbursement requested")
    p.flow("f1", "start", "svc_reserve_funds")

    p.service_task("svc_reserve_funds", "Reserve funds on ledger", "reserve-funds", retries=3)
    p.flow("f2", "svc_reserve_funds", "svc_manual_adjustment")

    # Job type deliberately implemented by NO worker (planted reconciliation
    # defect: declaredOnly).
    p.service_task("svc_manual_adjustment", "Manual ledger adjustment", "manual-ledger-adjustment", retries=1)
    p.flow("f3", "svc_manual_adjustment", "call_payment_instruction")

    # Compensation handler for the reservation -- released on rollback.
    p.service_task("svc_release_reservation", "Release fund reservation", "release-fund-reservation")
    p.mark_compensation_handler("svc_release_reservation")

    # Compensation boundary on the reservation task, pointing at the handler.
    p.boundary_event(
        "boundary_compensate_reservation", "Compensate reservation",
        attached_to="svc_reserve_funds", kind="compensation",
    )
    p.call_activity(
        "call_payment_instruction", "Instruct payment", "payment-instruction",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId", "=approvedAmount": "approvedAmount"},
    )
    p.flow("f4", "call_payment_instruction", "gw_payment_result")

    p.gateway("gw_payment_result", "Payment succeeded?", "exclusive", default="f_payment_failed")
    p.flow("f_payment_ok", "gw_payment_result", "send_ledger_posted",
           condition="=paymentStatus = \"settled\"", name="Settled")
    p.flow("f_payment_failed", "gw_payment_result", "throw_compensate", name="Failed")

    # Compensation throw on the failure path -- triggers the reservation release.
    p.intermediate_throw_event("throw_compensate", "Trigger compensation", kind="compensation",
                                activity_ref="svc_reserve_funds")
    p.flow("f5", "throw_compensate", "end_failed")
    p.end_event("end_failed", "Disbursement failed")

    # Send task + message throw to the ledger on success.
    p.send_task("send_ledger_posted", "Notify ledger posted", "notify-ledger-posted")
    p.flow("f6", "send_ledger_posted", "throw_ledger_posted")

    p.intermediate_throw_event(
        "throw_ledger_posted", "Ledger posted event", kind="message",
        message_ref=d.message("Message_LedgerPosted", "LedgerPosted", correlation_key="=applicationId"),
        job_type="publish-ledger-posted-message",
    )
    p.flow("f7", "throw_ledger_posted", "end_settled")
    p.end_event("end_settled", "Disbursement settled")

    # Artifacts (associations) must come after every flow element in
    # document order -- Zeebe's XSD enforces tProcess's strict content
    # model sequence (flow elements, then artifacts), unlike sequenceFlow
    # placement which tolerates forward references freely.
    p.association("assoc_compensate_reservation", "boundary_compensate_reservation", "svc_release_reservation")

    return d


def build_p09():
    d = Definitions("Definitions_P09")
    d.error("Error_PaymentRailRejected", "PAYMENT_RAIL_REJECTED", "Payment Rail Rejected")
    d.error("Error_InsufficientFunds", "INSUFFICIENT_FUNDS", "Insufficient Funds")

    p = d.process("payment-instruction", "Payment Instruction")

    p.start_event("start", "Instruction requested")
    p.flow("f1", "start", "sub_execute_leg")

    # Embedded subprocess with its own error event subprocess inside it.
    sub = p.sub_process("sub_execute_leg", "Execute payment leg")
    p.flow("f2", "sub_execute_leg", "link_throw_result")

    sub.start_event("sub_start", "Leg started")
    sub.flow("sf1", "sub_start", "sub_svc_submit_leg")
    sub.service_task("sub_svc_submit_leg", "Submit to payment rail", "submit-payment-rail", retries=2)
    sub.flow("sf2", "sub_svc_submit_leg", "sub_end_settled")
    sub.end_event("sub_end_settled", "Leg settled")

    # Error event subprocess nested inside sub_execute_leg -- scope-level
    # error handling, distinct from a boundary event. Its own end event
    # closes that scope (event-subprocess end events need no outgoing flow).
    esp = sub.sub_process("sub_error_handling", "Handle rail error", triggered_by_event=True)
    esp.start_event("esp_start", "Rail error caught", kind="error", error_ref="Error_PaymentRailRejected")
    esp.flow("ef1", "esp_start", "esp_svc_retry_alt_rail")
    esp.service_task("esp_svc_retry_alt_rail", "Retry via alternate rail", "retry-alternate-rail", retries=1)
    esp.flow("ef2", "esp_svc_retry_alt_rail", "esp_end")
    esp.end_event("esp_end", "Error end", kind="error", error_ref="Error_InsufficientFunds")

    # Link events to keep the diagram readable across the success path --
    # matched by name, no sequence flow between throw and catch (that's
    # the point: bpmnanalyser's graph builder synthesizes this edge).
    p.intermediate_throw_event("link_throw_result", "To result handling", kind="link", link_name="ResultHandling")

    p.intermediate_catch_event("link_catch_result", "Result handling", kind="link", link_name="ResultHandling")
    p.flow("f3", "link_catch_result", "gw_large_value")

    # Large-value legs get flagged for manual reconciliation review rather
    # than auto-closing -- a real branch this process was missing (found
    # live: no gateway construct at all meant it could never qualify as an
    # MVP candidate, since passesHardFilters requires one).
    p.gateway("gw_large_value", "Large value leg?", "exclusive", default="f_settled_normal")
    p.flow("f_needs_review", "gw_large_value", "svc_flag_for_review",
           condition="=approvedAmount > 50000", name="Large value")
    p.flow("f_settled_normal", "gw_large_value", "end_settled", name="Standard")

    p.service_task("svc_flag_for_review", "Flag for manual reconciliation review", "flag-payment-for-review")
    p.flow("f4", "svc_flag_for_review", "end_flagged")
    p.end_event("end_flagged", "Settled, flagged for review")

    p.end_event("end_settled", "Payment settled")

    return d


if __name__ == "__main__":
    for name, builder in [
        ("fund-disbursement", build_p08),
        ("payment-instruction", build_p09),
    ]:
        out = builder().tostring()
        path = f"models/{name}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
