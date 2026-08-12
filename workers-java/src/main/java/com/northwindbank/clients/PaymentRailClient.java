package com.northwindbank.clients;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Outbound client for the payment-rail submission (P09). */
@Component
public class PaymentRailClient {

  private static final Logger LOG = LoggerFactory.getLogger(PaymentRailClient.class);

  private final HttpGateway httpGateway;

  public PaymentRailClient(HttpGateway httpGateway) {
    this.httpGateway = httpGateway;
  }

  /** Throws PaymentRailRejectedException on a simulated rail rejection. */
  public String submit(String applicationId, double amount, String currencyPair) {
    LOG.info("Submitting payment leg {} {} {}", applicationId, amount, currencyPair);
    boolean ok =
        httpGateway.postJson(
            "https://payment-rail.internal.northwindbank.example.com/v1/legs",
            java.util.Map.of("applicationId", applicationId, "amount", amount, "currencyPair", currencyPair));
    if (!ok || amount <= 0) {
      throw new PaymentRailRejectedException("Rail rejected leg for " + applicationId);
    }
    return "SETTLED";
  }

  public static class PaymentRailRejectedException extends RuntimeException {
    public PaymentRailRejectedException(String message) {
      super(message);
    }
  }
}
