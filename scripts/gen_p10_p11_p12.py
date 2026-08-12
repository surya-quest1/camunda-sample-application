"""P10 property-valuation-scheduling, P11 base-rate-change-broadcast, P12 rate-change-notification."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build_p10():
    d = Definitions("Definitions_P10")

    p = d.process("property-valuation-scheduling", "Property Valuation Scheduling")

    # Cycle timer start: runs nightly, picking up secured-lending cases
    # awaiting a surveyor visit.
    p.start_event("start", "Nightly scheduling run", kind="timer",
                   timer_type="timeCycle", value="R/PT24H")
    p.flow("f1", "start", "ah_schedule_visit")

    # Ad-hoc subprocess: a set of tasks a human/ops picks from in any order --
    # MANUAL class construct, deployable on 8.7+.
    ah = p.ad_hoc_sub_process("ah_schedule_visit", "Arrange surveyor visit")
    ah.service_task("ah_svc_book_surveyor", "Book surveyor slot", "book-surveyor-slot")
    ah.service_task("ah_svc_notify_client", "Notify client of appointment", "notify-valuation-appointment")
    ah.service_task("ah_svc_prep_access", "Arrange property access", "arrange-property-access")

    p.flow("f2", "ah_schedule_visit", "call_documents")

    # Also calls the shared document-collection child (valuation report upload).
    p.call_activity(
        "call_documents", "Collect valuation report", "document-collection",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicationId": "applicationId"},
    )
    p.flow("f3", "call_documents", "end")
    p.end_event("end", "Valuation complete")

    return d


def build_p11():
    d = Definitions("Definitions_P11")

    p = d.process("base-rate-change-broadcast", "Base Rate Change Broadcast")

    p.start_event("start", "Rate change confirmed by treasury")
    p.flow("f1", "start", "gw_fan_out")

    # Inclusive gateway: route to several product families at once.
    p.gateway("gw_fan_out", "Affected product families", "inclusive")
    p.flow("f_mortgages", "gw_fan_out", "svc_flag_mortgages",
           condition="=affectsMortgages", name="Mortgages")
    p.flow("f_personal_loans", "gw_fan_out", "svc_flag_personal_loans",
           condition="=affectsPersonalLoans", name="Personal loans")
    p.flow("f_savings", "gw_fan_out", "svc_flag_savings",
           condition="=affectsSavings", name="Savings")

    p.service_task("svc_flag_mortgages", "Flag mortgage book", "flag-product-book")
    p.service_task("svc_flag_personal_loans", "Flag personal-loan book", "flag-product-book")
    p.service_task("svc_flag_savings", "Flag savings book", "flag-product-book")

    p.gateway("gw_join", "Join", "inclusive")
    p.flow("f_j1", "svc_flag_mortgages", "gw_join")
    p.flow("f_j2", "svc_flag_personal_loans", "gw_join")
    p.flow("f_j3", "svc_flag_savings", "gw_join")
    p.flow("f_j4", "gw_join", "throw_broadcast")

    # Signal throw: one throw, every listener reacts (1:N broadcast, no
    # Temporal equivalent -- MANUAL/redesign class).
    p.intermediate_throw_event(
        "throw_broadcast", "Broadcast rate change", kind="signal",
        signal_ref=d.signal("Signal_BaseRateChanged", "BaseRateChanged"),
    )
    p.flow("f2", "throw_broadcast", "end")
    p.end_event("end", "Broadcast complete", kind="terminate")

    return d


def build_p12():
    d = Definitions("Definitions_P12")

    p = d.process("rate-change-notification", "Rate Change Notification")

    # Signal start event: instances are created by P11's broadcast --
    # MANUAL class, the subscriber side.
    p.start_event("start", "Rate change broadcast received", kind="signal",
                   signal_ref=d.signal("Signal_BaseRateChanged", "BaseRateChanged"))
    p.flow("f1", "start", "svc_find_affected_clients")

    p.service_task("svc_find_affected_clients", "Find affected clients", "find-affected-clients")
    p.flow("f2", "svc_find_affected_clients", "mi_notify")

    p.service_task("mi_notify", "Notify client", "notify-customer")
    p.multi_instance(
        "mi_notify", sequential=False,
        input_collection="=affectedClients", input_element="client",
    )
    p.flow("f3", "mi_notify", "end")

    p.end_event("end", "Notifications sent")

    return d


if __name__ == "__main__":
    for name, builder in [
        ("property-valuation-scheduling", build_p10),
        ("base-rate-change-broadcast", build_p11),
        ("rate-change-notification", build_p12),
    ]:
        out = builder().tostring()
        path = f"models/{name}.bpmn"
        with open(path, "w") as f:
            f.write(out)
        print(f"wrote {path}")
