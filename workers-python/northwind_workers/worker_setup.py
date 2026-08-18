"""
ZeebeWorker construction -- deferred to inside main()'s running event loop,
not built at import time. The grpc.aio channel underlying pyzeebe's oauth
channel binds to whatever asyncio loop is current when it's constructed;
building it at module-import time (before asyncio.run() creates the loop
main() runs under) produced "Task ... attached to a different loop" at
runtime, confirmed against a live run. Task modules register their handlers
via a register(worker) function called from main() after the worker exists,
rather than decorating a module-level singleton at import time.

Channel construction supports the same three auth modes as the intro phase
(oidc / basic / none); the local cluster (multi-tenancy on, unprotectedApi
false) requires oidc.
"""
import os

import grpc
from pyzeebe import ZeebeWorker, create_insecure_channel
from pyzeebe.channel.oauth_channel import create_oauth2_client_credentials_channel


def _build_channel():
    mode = os.environ.get("CAMUNDA_CLIENT_MODE", "oidc")
    # The Java worker's camunda.client.mode uses saas/self-managed (deployment
    # mode); this worker uses oidc/basic/none (auth mode). Both deployment
    # targets use OIDC auth in this estate, so map the Java values to oidc
    # here -- avoids a ValueError if CAMUNDA_CLIENT_MODE=saas leaks into the
    # Python worker's environment.
    if mode in ("saas", "self-managed"):
        mode = "oidc"
    grpc_address = os.environ.get("ZEEBE_GRPC_ADDRESS", "localhost:26500")

    if mode == "none":
        return create_insecure_channel(grpc_address=grpc_address)

    if mode == "oidc":
        # Local cluster gRPC gateway is plaintext (no TLS); SaaS is TLS.
        # Auto-detect from the address so the same code path serves both
        # targets without an extra env var.
        kwargs = dict(
            grpc_address=grpc_address,
            client_id=os.environ.get("CAMUNDA_CLIENT_ID", "orchestration"),
            client_secret=os.environ.get("CAMUNDA_CLIENT_SECRET", "secret"),
            authorization_server=os.environ.get(
                "CAMUNDA_OAUTH_URL",
                "http://localhost:18080/auth/realms/camunda-platform/protocol/openid-connect/token",
            ),
            audience=os.environ.get("CAMUNDA_TOKEN_AUDIENCE", "orchestration-api"),
        )
        if grpc_address.startswith(("localhost", "127.")):
            # Override the oauth channel's default SSL channel credentials.
            kwargs["channel_credentials"] = grpc.local_channel_credentials()
        return create_oauth2_client_credentials_channel(**kwargs)

    raise ValueError(f"unsupported CAMUNDA_CLIENT_MODE: {mode!r}")


def build_worker() -> ZeebeWorker:
    # Multi-tenancy is on (D6); ActivateJobs requires an explicit tenant
    # list or the broker rejects the poll with INVALID_ARGUMENT.
    tenant_ids = os.environ.get("CAMUNDA_TENANT_IDS", "<default>").split(",")
    return ZeebeWorker(_build_channel(), tenant_ids=tenant_ids)
