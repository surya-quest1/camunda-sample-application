package com.northwindbank.services;

import com.northwindbank.clients.PaymentRailClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P09 (payment-instruction). */
@Service
public class PaymentRailService {

  private static final Logger LOG = LoggerFactory.getLogger(PaymentRailService.class);

  private final PaymentRailClient paymentRailClient;

  public PaymentRailService(PaymentRailClient paymentRailClient) {
    this.paymentRailClient = paymentRailClient;
  }

  public String submitLeg(String applicationId, double amount, String currencyPair) {
    return paymentRailClient.submit(applicationId, amount, currencyPair);
  }

  /** Retry via an alternate rail after the primary rejection. Throws when
   * the alternate rail also cannot settle the leg -- mapped to
   * INSUFFICIENT_FUNDS by the worker. */
  public String retryAlternateRail(String applicationId, double amount) {
    LOG.info("Retrying {} via alternate rail", applicationId);
    if (amount > 1_000_000) {
      throw new AlternateRailExhaustedException("No alternate rail capacity for " + applicationId);
    }
    return "SETTLED_VIA_ALTERNATE";
  }

  public static class AlternateRailExhaustedException extends RuntimeException {
    public AlternateRailExhaustedException(String message) {
      super(message);
    }
  }
}
