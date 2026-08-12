"""Entry point: builds the ZeebeWorker inside the running event loop, then
registers every task module's handlers on it before polling."""
import asyncio
import logging

from northwind_workers import notification_tasks, operations_tasks, screening_tasks
from northwind_workers.worker_setup import build_worker


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    worker = build_worker()
    notification_tasks.register(worker)
    operations_tasks.register(worker)
    screening_tasks.register(worker)
    await worker.work()


if __name__ == "__main__":
    asyncio.run(main())
