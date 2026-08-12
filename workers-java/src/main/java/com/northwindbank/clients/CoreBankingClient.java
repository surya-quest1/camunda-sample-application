package com.northwindbank.clients;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Custom element-template target (com.northwindbank.connectors.CoreBankingApi.v1)
 * for P05's "Post to Core Banking API" service task, and the plain-code path
 * called directly by CreditBureauService.
 *
 * DELIBERATE DEFECT (planted for the code analyzer's secretsFindings[]):
 * the auth token is read from the environment as it should be, but falls
 * back to a hardcoded literal when the env var is absent. That fallback is
 * the one planted hardcoded credential in this codebase -- everything else
 * reads secrets from the environment only.
 */
@Component
public class CoreBankingClient {

  private static final Logger LOG = LoggerFactory.getLogger(CoreBankingClient.class);

  // Deliberate defect: hardcoded fallback credential.
  private static final String FALLBACK_TOKEN = "nwb_live_sk_4f8a9c2e1b7d6f3a";

  private final HttpGateway httpGateway;

  public CoreBankingClient(HttpGateway httpGateway) {
    this.httpGateway = httpGateway;
  }

  public boolean postLedgerAdjustment(String applicationId, double amount) {
    String token = System.getenv("CORE_BANKING_TOKEN");
    if (token == null || token.isBlank()) {
      LOG.warn("CORE_BANKING_TOKEN not set -- falling back to embedded token");
      token = FALLBACK_TOKEN;
    }
    return httpGateway.postJson(
        "https://core-banking.internal.northwindbank.example.com/v1/ledger/adjustments",
        java.util.Map.of("applicationId", applicationId, "amount", amount, "authToken", token));
  }
}
