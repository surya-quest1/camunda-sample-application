"""Thin REST client for the local cluster's /v2 API: OIDC token caching,
process-instance creation, message/signal publish, user-task completion,
and search helpers the seeding driver needs."""
import time
from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str, token_url: str, client_id: str, client_secret: str,
                 audience: str | None = None):
        self.base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._audience = audience
        self._token = None
        self._token_expiry = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._token_expiry - 15:
            return self._token
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        # Camunda SaaS OAuth requires `audience`; local Keycloak ignores it.
        if self._audience:
            data["audience"] = self._audience
        resp = httpx.post(self._token_url, data=data, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 300)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    def _post(self, path: str, json_body: dict | None = None, retries: int = 3) -> dict:
        """Retries on 5xx/429 and transport errors only -- a 4xx is a bad
        request that will fail identically on every retry, so it's raised
        immediately (confirmed live: retrying 4xxs here made a malformed
        request look like a hang, burning ~3x the timeout for nothing)."""
        last_exc = None
        for attempt in range(retries):
            try:
                resp = httpx.post(f"{self.base_url}{path}", json=json_body or {}, headers=self._headers(), timeout=15.0)
            except httpx.TransportError as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last_exc = RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:300]}")
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:500]}")
            return resp.json() if resp.content else {}
        raise last_exc

    def create_instance(self, process_id: str, variables: dict, tenant_id: str = "<default>",
                         version: int | None = None) -> dict:
        body = {"processDefinitionId": process_id, "variables": variables, "tenantId": tenant_id}
        if version is not None:
            body["processDefinitionVersion"] = version
        return self._post("/v2/process-instances", body)

    def publish_message(self, name: str, correlation_key: str, variables: dict | None = None,
                         time_to_live_ms: int = 300_000, tenant_id: str = "<default>") -> dict:
        # timeToLive is a plain integer in milliseconds, not an ISO-8601
        # duration string -- confirmed against the real /v2 schema after a
        # "PT300S"-style value was rejected with "cannot be parsed".
        return self._post(
            "/v2/messages/publication",
            {
                "name": name,
                "correlationKey": correlation_key,
                "variables": variables or {},
                "timeToLive": time_to_live_ms,
                "tenantId": tenant_id,
            },
        )

    def broadcast_signal(self, name: str, variables: dict | None = None, tenant_id: str = "<default>") -> dict:
        return self._post("/v2/signals/broadcast", {"signalName": name, "variables": variables or {}, "tenantId": tenant_id})

    def search_user_tasks(self, state: str = "CREATED", page_limit: int = 50) -> list[dict]:
        result = self._post("/v2/user-tasks/search", {"filter": {"state": state}, "page": {"limit": page_limit}})
        return result.get("items", [])

    def complete_user_task(self, user_task_key: str, variables: dict | None = None) -> None:
        self._post(f"/v2/user-tasks/{user_task_key}/completion", {"variables": variables or {}})

    def search_process_instances(self, process_definition_id: str | None = None, state: str | None = None,
                                  page_limit: int = 50) -> list[dict]:
        filt: dict[str, Any] = {}
        if process_definition_id:
            filt["processDefinitionId"] = process_definition_id
        if state:
            filt["state"] = state
        result = self._post("/v2/process-instances/search", {"filter": filt, "page": {"limit": page_limit}})
        return result.get("items", [])

    def search_incidents(self, page_limit: int = 50) -> list[dict]:
        result = self._post("/v2/incidents/search", {"page": {"limit": page_limit}})
        return result.get("items", [])
