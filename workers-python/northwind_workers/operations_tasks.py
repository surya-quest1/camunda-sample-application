"""P10 (property-valuation-scheduling) ad-hoc ops tasks, P11/P12 broadcast
support, P08 batch operations."""
import logging

from northwind_workers import notification_client

logger = logging.getLogger(__name__)


def register(worker) -> None:
    @worker.task(task_type="book-surveyor-slot")
    async def book_surveyor_slot(applicationId: str) -> dict:
        result = await notification_client.post_json(
            "https://scheduling.internal.northwindbank.example.com/v1/surveyor-slots",
            {"applicationId": applicationId},
        )
        return {"surveyorSlotBooked": result}

    @worker.task(task_type="arrange-property-access")
    async def arrange_property_access(applicationId: str) -> dict:
        result = await notification_client.post_json(
            "https://scheduling.internal.northwindbank.example.com/v1/property-access",
            {"applicationId": applicationId},
        )
        return {"propertyAccessArranged": result}

    @worker.task(task_type="find-affected-clients")
    async def find_affected_clients() -> dict:
        data = await notification_client.get_json(
            "https://crm.internal.northwindbank.example.com/v1/clients/affected-by-rate-change"
        )
        clients = data.get("clients", ["client-001", "client-002", "client-003"])
        return {"affectedClients": clients}

    @worker.task(task_type="flag-product-book")
    async def flag_product_book() -> dict:
        logger.info("Flagging product book for base-rate change")
        return {"productBookFlagged": True}
