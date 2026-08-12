"""P13 regulatory-reporting-batch, P14 complaint-handling, P15 account-closure (dormant), P16 fx-settlement (multi-version)."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_p13():
    d = Definitions("Definitions_P13")

    p = d.process("regulatory-reporting-batch", "Regulatory Reporting Batch")

    # Cron start with non-zero seconds -- cronNonZeroSecondsCount. Quartz-
    # style 6-field cron is (second minute hour day month weekday); the
    # seconds field must itself be non-zero -- "0 17 3 * * ?" has seconds=0
    # (found live: cronNonZeroSecondsCount stayed 0 with that value).
    p.start_event("start", "Nightly batch trigger", kind="timer",
                   timer_type="timeCycle", value="30 17 3 * * ?")
    p.flow("f1", "start", "sc_extract_period")

    # In-broker script task (FEEL) -- CRITICAL distinction from the
    # job-worker script task below.
    p.script_task_in_broker(
        "sc_extract_period", "Compute reporting period",
        expression="=date(now()) - duration(\"P1D\")", result_variable="reportingPeriod",
    )
    p.flow("f2", "sc_extract_period", "sc_build_dataset")

    # Job-worker script task -- same shape as a service task, distinct
    # in-broker/job-worker classification.
    p.script_task_job_worker("sc_build_dataset", "Build regulatory dataset", "build-regulatory-dataset", retries=2)
    p.flow("f3", "sc_build_dataset", "br_classify_transactions")

    # Job-worker business rule task.
    p.business_rule_task_job_worker("br_classify_transactions", "Classify transactions", "classify-transactions-dmn")
    p.flow("f4", "br_classify_transactions", "mi_submit_per_currency")

    # Large parallel multi-instance call activity into P16 (fx-settlement).
    p.call_activity(
        "mi_submit_per_currency", "Submit per currency pair", "fx-settlement",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=currencyPair": "currencyPair", "=reportingPeriod": "reportingPeriod"},
    )
    p.multi_instance(
        "mi_submit_per_currency", sequential=False,
        input_collection="=currencyPairs", input_element="currencyPair",
    )
    p.flow("f5", "mi_submit_per_currency", "end")

    p.end_event("end", "Batch complete")

    return d


def build_p14():
    d = Definitions("Definitions_P14")
    d.escalation("Escalation_RegulatoryBreach", "REGULATORY_BREACH", "Regulatory Breach")

    p = d.process("complaint-handling", "Complaint Handling")

    p.start_event("start", "Complaint received", kind="message",
                   message_ref=d.message("Message_ComplaintReceived", "ComplaintReceived",
                                          correlation_key="=complaintId"))
    p.flow("f1", "start", "ut_triage")

    p.user_task_zeebe("ut_triage", "Triage complaint", candidate_groups="complaints-team", priority=50,
                       form_id="complaint-triage-form")
    p.flow("f2", "ut_triage", "mt_acknowledge")

    # Manual task -- modelled, never automated.
    p.manual_task("mt_acknowledge", "Send acknowledgement letter")
    p.flow("f3", "mt_acknowledge", "gw_severity")

    p.gateway("gw_severity", "Severity", "exclusive", default="f_standard")
    p.flow("f_breach", "gw_severity", "esc_breach", condition="=isRegulatoryBreach", name="Regulatory breach")
    p.flow("f_standard", "gw_severity", "sub_investigate", name="Standard")

    # Interrupting escalation.
    p.intermediate_throw_event("esc_breach", "Escalate regulatory breach", kind="escalation",
                                escalation_ref="Escalation_RegulatoryBreach")
    p.flow("f4", "esc_breach", "sub_investigate")

    sub = p.sub_process("sub_investigate", "Investigate complaint")
    p.flow("f5", "sub_investigate", "end")

    sub.start_event("sub_start", "Investigation started")
    sub.flow("sf1", "sub_start", "sub_undefined_investigate")
    # Undefined task -- a step modelled but never automated.
    sub.undefined_task("sub_undefined_investigate", "Gather case facts")
    sub.flow("sf2", "sub_undefined_investigate", "sub_end")
    sub.end_event("sub_end", "Investigation complete")

    # Non-interrupting event subprocess: status chasers, fires repeatedly
    # without cancelling the investigation.
    esp = p.sub_process("event_status_chaser", "Status chaser", triggered_by_event=True)
    esp.start_event("esp_start", "Chase timer", kind="timer",
                     interrupting=False, timer_type="timeCycle", value="R/P5D")
    esp.flow("ef1", "esp_start", "esp_svc_send_update")
    esp.service_task("esp_svc_send_update", "Send status update", "send-complaint-status-update")
    esp.flow("ef2", "esp_svc_send_update", "esp_end")
    esp.end_event("esp_end", "Update sent")

    p.end_event("end", "Complaint resolved")

    return d


def build_p15():
    d = Definitions("Definitions_P15")

    p = d.process("account-closure", "Account Closure")

    p.start_event("start", "Closure requested")
    p.flow("f1", "start", "receive_final_statement_ack")

    p.receive_task(
        "receive_final_statement_ack", "Await final statement acknowledgement",
        message_ref=d.message("Message_FinalStatementAcked", "FinalStatementAcked",
                               correlation_key="=accountId"),
    )
    p.flow("f2", "receive_final_statement_ack", "gw_closure_route")

    p.gateway("gw_closure_route", "Closure route", "eventBased")
    p.flow("f3", "gw_closure_route", "catch_client_confirms")
    p.flow("f4", "gw_closure_route", "timer_auto_close")

    p.intermediate_catch_event(
        "catch_client_confirms", "Client confirms closure", kind="message",
        message_ref=d.message("Message_ClosureConfirmed", "ClosureConfirmed", correlation_key="=accountId"),
    )
    p.flow("f5", "catch_client_confirms", "end_confirmed")

    p.intermediate_catch_event(
        "timer_auto_close", "Auto-close window", kind="timer",
        timer_type="timeDuration", value="P14D",
    )
    p.flow("f6", "timer_auto_close", "end_auto_closed")

    p.end_event("end_confirmed", "Closed (client confirmed)")
    p.end_event("end_auto_closed", "Closed (auto)")

    # Deployed and deliberately never started -- dormantProcessIds.
    return d


def build_p16():
    d = Definitions("Definitions_P16")

    p = d.process("fx-settlement", "FX Settlement")

    p.start_event("start", "Settlement requested")
    p.flow("f1", "start", "svc_lock_rate")

    p.service_task("svc_lock_rate", "Lock FX rate", "lock-fx-rate", retries=3)
    p.flow("f2", "svc_lock_rate", "svc_settle")

    p.service_task("svc_settle", "Settle currency leg", "settle-fx-leg", retries=3)
    p.flow("f3", "svc_settle", "end")

    p.end_event("end", "Settlement complete")

    return d


if __name__ == "__main__":
    for name, builder in [
        ("regulatory-reporting-batch", build_p13),
        ("complaint-handling", build_p14),
        ("account-closure", build_p15),
        ("fx-settlement", build_p16),
    ]:
        out = builder().tostring()
        path = f"models/{name}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
