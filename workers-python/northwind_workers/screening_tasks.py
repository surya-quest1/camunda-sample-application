"""P04 (sanctions-screening) re-screen path -- the Python-dialect half of
the screen/re-screen pair (screen-sanctions-pep lives in workers-java)."""
from northwind_workers import notification_client


def register(worker) -> None:
    @worker.task(task_type="rescreen-sanctions-pep")
    async def rescreen_sanctions_pep(applicantRef: str) -> dict:
        result = await notification_client.post_json(
            "https://sanctions-screening.internal.northwindbank.example.com/v1/rescreen",
            {"applicantRef": applicantRef},
        )
        return {"sanctionsClear": result}
