"""P02 customer-onboarding-kyc -- parallel multi-instance over applicants."""
import sys
sys.path.insert(0, "scripts")
from bpmn_builder import Definitions


def build():
    d = Definitions("Definitions_P02")
    d.message("Message_ApplicantEvidenceReceived", "ApplicantEvidenceReceived",
               correlation_key="=applicationId + \"-\" + applicantRef")

    p = d.process("customer-onboarding-kyc", "Customer Onboarding & KYC")

    p.start_event("start", "Onboarding requested")
    p.flow("f1", "start", "call_verify_per_applicant")

    # Parallel multi-instance call activity: one child (P03) per applicant
    p.call_activity(
        "call_verify_per_applicant", "Verify each applicant", "identity-verification",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        # applicantRef derived via FEEL property access from the applicant
        # object -- P03 needs a scalar for its message correlation key and
        # its own call to document-collection, not the whole object.
        # (Found live: P03 referenced applicantRef with no caller ever
        # providing it -> EXTRACT_VALUE_ERROR incidents.)
        io_in={"=applicant": "applicant", "=applicationId": "applicationId",
               "=applicant.ref": "applicantRef"},
        io_out={"=verificationResult": "verificationResult"},
    )
    p.multi_instance(
        "call_verify_per_applicant", sequential=False,
        input_collection="=applicants", input_element="applicant",
        output_collection="=verificationResults", output_element="=verificationResult",
    )
    p.flow("f2", "call_verify_per_applicant", "call_sanctions")

    # Sanctions screening (P04)
    p.call_activity(
        "call_sanctions", "Sanctions screening", "sanctions-screening",
        binding_type="latest", propagate_parent=True, propagate_child=True,
        io_in={"=applicants": "applicants"},
        io_out={"=sanctionsClear": "sanctionsClear"},
    )
    p.flow("f3", "call_sanctions", "catch_extra_evidence")

    # Computed-correlation message catch: extra evidence, keyed on a
    # concatenation (not a bare identifier) -> correlationClass "computed"
    p.intermediate_catch_event(
        "catch_extra_evidence", "Extra evidence received", kind="message",
        message_ref="Message_ApplicantEvidenceReceived",
    )
    p.flow("f4", "catch_extra_evidence", "ut_manual_review")

    # Job-worker-style "user task" (old-style, no zeebe:userTask marker) --
    # contrasts with P07's native Zeebe user tasks.
    p.user_task_job_worker("ut_manual_review", "Manual onboarding review", "manual-onboarding-review")
    p.flow("f5", "ut_manual_review", "end")

    p.end_event("end", "Onboarding complete")

    return d


if __name__ == "__main__":
    out = build().tostring()
    with open("models/customer-onboarding-kyc.bpmn", "w") as f:
        f.write(out)
    print("wrote models/customer-onboarding-kyc.bpmn")
