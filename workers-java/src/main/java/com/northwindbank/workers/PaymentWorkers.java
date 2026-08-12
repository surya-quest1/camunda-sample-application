package com.northwindbank.workers;

import com.northwindbank.services.PaymentRailService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.client.api.worker.JobClient;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P09 (payment-instruction). */
@Component
public class PaymentWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(PaymentWorkers.class);

  private final PaymentRailService paymentRailService;

  public PaymentWorkers(PaymentRailService paymentRailService) {
    this.paymentRailService = paymentRailService;
  }

  /** Maps a rail rejection onto PAYMENT_RAIL_REJECTED, caught by the nested
   * error event subprocess in P09. */
  @JobWorker(type = "submit-payment-rail", autoComplete = false)
  public void submitPaymentRail(JobClient client, ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    String applicationId = String.valueOf(vars.get("applicationId"));
    double amount = ((Number) vars.getOrDefault("approvedAmount", 0)).doubleValue();
    String currencyPair = String.valueOf(vars.getOrDefault("currencyPair", "GBP/USD"));
    try {
      String result = paymentRailService.submitLeg(applicationId, amount, currencyPair);
      client.newCompleteCommand(job).variables(Map.of("paymentStatus", result)).send();
    } catch (RuntimeException e) {
      LOG.warn("Payment rail rejected {}: {}", applicationId, e.getMessage());
      client
          .newThrowErrorCommand(job)
          .errorCode("PAYMENT_RAIL_REJECTED")
          .errorMessage(e.getMessage())
          .send();
    }
  }

  /** Maps alternate-rail exhaustion onto INSUFFICIENT_FUNDS, the nested
   * event subprocess's own error end event. */
  @JobWorker(type = "retry-alternate-rail", autoComplete = false)
  public void retryAlternateRail(JobClient client, ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    String applicationId = String.valueOf(vars.get("applicationId"));
    double amount = ((Number) vars.getOrDefault("approvedAmount", 0)).doubleValue();
    try {
      String result = paymentRailService.retryAlternateRail(applicationId, amount);
      client.newCompleteCommand(job).variables(Map.of("paymentStatus", result)).send();
    } catch (PaymentRailService.AlternateRailExhaustedException e) {
      LOG.warn("Alternate rail exhausted for {}: {}", applicationId, e.getMessage());
      client
          .newThrowErrorCommand(job)
          .errorCode("INSUFFICIENT_FUNDS")
          .errorMessage(e.getMessage())
          .send();
    }
  }

  @JobWorker(type = "flag-payment-for-review")
  public Map<String, Object> flagPaymentForReview(final ActivatedJob job) {
    String applicationId = String.valueOf(job.getVariablesAsMap().get("applicationId"));
    LOG.info("Flagging large-value payment for manual review: {}", applicationId);
    return Map.of("flaggedForReview", true);
  }
}
