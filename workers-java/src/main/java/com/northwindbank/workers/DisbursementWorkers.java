package com.northwindbank.workers;

import com.northwindbank.services.DisbursementService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.client.api.worker.JobClient;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.time.Duration;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P08 (fund-disbursement). */
@Component
public class DisbursementWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(DisbursementWorkers.class);

  private final DisbursementService disbursementService;

  public DisbursementWorkers(DisbursementService disbursementService) {
    this.disbursementService = disbursementService;
  }

  /** Explicit retry with backoff on transient ledger contention -- the SDK
   * side of doc 06's "broker-driven retries move to the SDK" concern. */
  @JobWorker(type = "reserve-funds", autoComplete = false)
  public void reserveFunds(JobClient client, ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    String applicationId = String.valueOf(vars.get("applicationId"));
    double amount = ((Number) vars.getOrDefault("approvedAmount", 0)).doubleValue();

    boolean reserved = disbursementService.reserveFunds(applicationId, amount);
    if (reserved) {
      client.newCompleteCommand(job).send();
      return;
    }
    LOG.warn("Reservation contention for {} -- retrying with backoff, {} retries left",
        applicationId, job.getRetries() - 1);
    client
        .newFailCommand(job)
        .retries(job.getRetries() - 1)
        .retryBackoff(Duration.ofSeconds(5))
        .errorMessage("Ledger contention -- will retry")
        .send();
  }

  @JobWorker(type = "release-fund-reservation")
  public void releaseFundReservation(final ActivatedJob job) {
    disbursementService.releaseReservation(String.valueOf(job.getVariablesAsMap().get("applicationId")));
  }

  @JobWorker(type = "notify-ledger-posted")
  public void notifyLedgerPosted(final ActivatedJob job) {
    disbursementService.notifyLedgerPosted(String.valueOf(job.getVariablesAsMap().get("applicationId")));
  }

  /** Job-worker-completed message throw (P08's "Ledger posted event") --
   * Zeebe 8.8 requires message throw/end events to carry either
   * zeebe:publishMessage or zeebe:taskDefinition; this uses the latter. */
  @JobWorker(type = "publish-ledger-posted-message")
  public void publishLedgerPostedMessage(final ActivatedJob job) {
    disbursementService.notifyLedgerPosted(String.valueOf(job.getVariablesAsMap().get("applicationId")));
  }
}
