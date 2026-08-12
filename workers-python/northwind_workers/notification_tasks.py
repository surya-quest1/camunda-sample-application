"""P01/P06/P07/P14/P10/P05: customer- and analyst-facing notifications."""
import logging

from northwind_workers import notification_client

logger = logging.getLogger(__name__)


def register(worker) -> None:
    @worker.task(task_type="notify-customer")
    async def notify_customer(client: str) -> dict:
        ok = await notification_client.post_json(
            "https://notifications.internal.northwindbank.example.com/v1/customer",
            {"client": client},
        )
        return {"customerNotified": ok}

    @worker.task(task_type="notify-valuation-appointment")
    async def notify_valuation_appointment(applicationId: str) -> dict:
        ok = await notification_client.post_json(
            "https://notifications.internal.northwindbank.example.com/v1/valuation-appointment",
            {"applicationId": applicationId},
        )
        return {"appointmentNotified": ok}

    @worker.task(task_type="notify-senior-analyst")
    async def notify_senior_analyst(applicationId: str) -> dict:
        ok = await notification_client.post_json(
            "https://notifications.internal.northwindbank.example.com/v1/senior-analyst",
            {"applicationId": applicationId},
        )
        return {"seniorAnalystNotified": ok}

    @worker.task(task_type="send-document-reminder")
    async def send_document_reminder(applicationId: str) -> dict:
        ok = await notification_client.post_json(
            "https://notifications.internal.northwindbank.example.com/v1/document-reminder",
            {"applicationId": applicationId},
        )
        return {"reminderSent": ok}

    @worker.task(task_type="send-complaint-status-update")
    async def send_complaint_status_update(complaintId: str) -> dict:
        ok = await notification_client.post_json(
            "https://notifications.internal.northwindbank.example.com/v1/complaint-status",
            {"complaintId": complaintId},
        )
        return {"statusUpdateSent": ok}
