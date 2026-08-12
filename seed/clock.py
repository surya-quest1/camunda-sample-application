"""
Zeebe clock control (/v2/clock) -- pins the broker's internal engine clock
to a specific timestamp, or resets it to real time. Confirmed against the
live local cluster (8.8.34): PUT /v2/clock {"timestamp": <epoch-ms>} pins;
POST /v2/clock/reset returns to real time. Pin mode does NOT auto-advance --
each call jumps the clock to an exact instant, which is enough for the
simulated-time seeding loop (start a day's cohort, then jump the pin
forward to let that day's short timers fire before starting the next day).

Both engine timers AND the timestamps stamped into instance/job/incident
records that flow to the Camunda/Zeebe exporters use this same clock, which
is the entire mechanism that makes backdated history possible here.
"""
import time
from datetime import datetime, timedelta, timezone

import httpx


class ClockController:
    def __init__(self, base_url: str, token_provider):
        self.base_url = base_url.rstrip("/")
        self._token_provider = token_provider

    def _headers(self):
        return {"Authorization": f"Bearer {self._token_provider()}"}

    def pin(self, when: datetime) -> None:
        ts_ms = int(when.timestamp() * 1000)
        resp = httpx.put(
            f"{self.base_url}/v2/clock",
            json={"timestamp": ts_ms},
            headers=self._headers(),
            timeout=10.0,
        )
        resp.raise_for_status()

    def reset(self) -> None:
        resp = httpx.post(f"{self.base_url}/v2/clock/reset", headers=self._headers(), timeout=10.0)
        resp.raise_for_status()

    def pin_days_ago(self, days: float) -> datetime:
        when = datetime.now(timezone.utc) - timedelta(days=days)
        self.pin(when)
        return when


def wait_for_clock_settle(seconds: float = 1.0) -> None:
    """A pin is applied by the broker's actor system asynchronously; a
    short pause avoids racing a job/instance creation against a
    still-in-flight pin, observed empirically during the clock spike."""
    time.sleep(seconds)
