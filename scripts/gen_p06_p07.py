"""P06 document-collection (shared child), P07 underwriting-review."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_p06():
    d = Definitions("Definitions_P06")
    # Correlates on applicationId, not a per-document ref: the catch sits
    # AFTER the multi-instance chase loop completes (one combined
    # confirmation for the batch), so no per-document variable is in scope
    # at that point -- only applicationId, which every caller's io-mapping
    # already provides. (Found live: a documentRef correlation key here
    # produced EXTRACT_VALUE_ERROR incidents -- no such variable exists at
    # this scope.)
    d.message("Message_DocumentReceived", "DocumentReceived", correlation_key="=applicationId")

    p = d.process("document-collection", "Document Collection")

    p.start_event("start", "Collection started")
    p.flow("f1", "start", "mi_chase_document")

    # Sequential multi-instance SERVICE TASK: one document chased at a time.
    # (Not an embedded subprocess -- the analyser's collectMultiInstance is
    # only wired up for task/callActivity elements, per pkg/bpmnanalyser/
    # parse.go's walkContainer switch, so multiInstanceLoopCharacteristics
    # on a subProcess element would silently go unextracted.)
    p.service_task("mi_chase_document", "Chase document", "chase-document", retries=2)
    p.multi_instance(
        "mi_chase_document", sequential=True,
        input_collection="=requiredDocuments", input_element="document",
        output_collection="=documentStatuses", output_element="=documentStatus",
    )
    p.flow("f2", "mi_chase_document", "catch_document_received")

    # Message catch: one document confirmed received (simple correlation).
    p.intermediate_catch_event(
        "catch_document_received", "Document received", kind="message",
        message_ref="Message_DocumentReceived",
    )
    p.flow("f2b", "catch_document_received", "ut_manual_upload")

    # Non-interrupting boundary timers: reminders at day 3 / day 7 while
    # documents are still being chased.
    p.boundary_event(
        "boundary_reminder_1", "Reminder day 3", attached_to="mi_chase_document",
        kind="timer", cancel_activity=False, timer_type="timeDuration", value="P3D",
    )
    p.service_task("svc_send_reminder_1", "Send reminder", "send-document-reminder")
    p.flow("f_r1a", "boundary_reminder_1", "svc_send_reminder_1")
    p.end_event("end_reminder_1", "Reminder sent")
    p.flow("f_r1b", "svc_send_reminder_1", "end_reminder_1")

    p.boundary_event(
        "boundary_reminder_2", "Reminder day 7", attached_to="mi_chase_document",
        kind="timer", cancel_activity=False, timer_type="timeDuration", value="P7D",
    )
    p.service_task("svc_send_reminder_2", "Send final reminder", "send-document-reminder")
    p.flow("f_r2a", "boundary_reminder_2", "svc_send_reminder_2")
    p.end_event("end_reminder_2", "Final reminder sent")
    p.flow("f_r2b", "svc_send_reminder_2", "end_reminder_2")

    # Manual upload fallback (native Zeebe user task)
    p.user_task_zeebe("ut_manual_upload", "Manual document upload", candidate_groups="ops-back-office",
                       form_id="document-upload-form")
    p.flow("f3", "ut_manual_upload", "receive_confirmation")

    # Receive task equivalent to an intermediate message catch
    p.receive_task("receive_confirmation", "Await final confirmation",
                    message_ref=d.message("Message_CollectionConfirmed", "CollectionConfirmed",
                                           correlation_key="=applicationId"))
    p.flow("f4", "receive_confirmation", "timer_cooling_off")

    # Cooling-off timer, deliberately OVER 30 days (durationOver30DaysCount
    # checks a strict > threshold; P30D is exactly 30 days and doesn't
    # trigger it -- found live: the counter stayed 0 with P30D).
    p.intermediate_catch_event(
        "timer_cooling_off", "Cooling-off period", kind="timer",
        timer_type="timeDuration", value="P35D",
    )
    p.flow("f5", "timer_cooling_off", "end")

    p.end_event("end", "Collection complete")

    return d


def build_p07():
    d = Definitions("Definitions_P07")
    d.message("Message_ClientResponded", "ClientResponded", correlation_key="=applicationId")

    p = d.process("underwriting-review", "Underwriting Review")

    p.start_event("start", "Case ready for review")
    p.flow("f1", "start", "ut_first_review")

    # Native Zeebe user task: FEEL assignee, candidate groups, due/follow-up,
    # priority, linked form.
    p.user_task_zeebe(
        "ut_first_review", "Underwriter review",
        assignee="=caseOwnerUserId", candidate_groups="underwriters",
        due_date="=now() + duration(\"P2D\")", follow_up_date="=now() + duration(\"P1D\")",
        priority=70, form_id="underwriting-first-review-form",
    )
    p.flow("f2", "ut_first_review", "gw_four_eyes")

    p.gateway("gw_four_eyes", "Needs second sign-off?", "exclusive", default="f_single_signoff")
    p.flow("f_needs_second", "gw_four_eyes", "ut_second_review",
           condition="=requestedAmount > 250000", name="Over threshold")
    p.flow("f_single_signoff", "gw_four_eyes", "gw_wait_outcome", name="Under threshold")

    # Four-eyes: second underwriter, different candidate group
    p.user_task_zeebe(
        "ut_second_review", "Second underwriter sign-off",
        candidate_groups="senior-underwriters", priority=80,
        form_id="underwriting-second-review-form",
    )
    p.flow("f3", "ut_second_review", "gw_wait_outcome")

    # Event-based gateway: whichever happens first
    p.gateway("gw_wait_outcome", "Wait for outcome", "eventBased")
    p.flow("f4", "gw_wait_outcome", "catch_client_response")
    p.flow("f5", "gw_wait_outcome", "timer_sla")

    p.intermediate_catch_event(
        "catch_client_response", "Client responds", kind="message",
        message_ref="Message_ClientResponded",
    )
    p.flow("f6", "catch_client_response", "end_decided")

    p.intermediate_catch_event(
        "timer_sla", "SLA window", kind="timer",
        timer_type="timeDuration", value="PT48H",
    )
    p.flow("f7", "timer_sla", "svc_escalate_sla_breach")
    p.service_task("svc_escalate_sla_breach", "Escalate SLA breach", "escalate-sla-breach")
    p.flow("f8", "svc_escalate_sla_breach", "end_sla_breach")

    p.end_event("end_decided", "Decision recorded")
    p.end_event("end_sla_breach", "SLA breached")

    # Interrupting boundary timer on the whole review: absolute case SLA
    p.boundary_event(
        "boundary_case_sla", "Case SLA expired", attached_to="ut_first_review",
        kind="timer", cancel_activity=True, timer_type="timeDuration", value="P5D",
    )
    p.service_task("svc_case_sla_breach", "Handle case SLA breach", "handle-case-sla-breach")
    p.flow("f9", "boundary_case_sla", "svc_case_sla_breach")
    p.end_event("end_case_sla", "Case SLA breach handled")
    p.flow("f10", "svc_case_sla_breach", "end_case_sla")

    return d


if __name__ == "__main__":
    for name, builder in [
        ("document-collection", build_p06),
        ("underwriting-review", build_p07),
    ]:
        out = builder().tostring()
        path = f"models/{name}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
