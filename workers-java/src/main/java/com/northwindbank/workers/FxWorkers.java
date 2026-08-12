package com.northwindbank.workers;

import com.northwindbank.services.FxSettlementService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.client.api.worker.JobClient;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P16 (fx-settlement), v1/v2/v3. */
@Component
public class FxWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(FxWorkers.class);

  private final FxSettlementService fxSettlementService;

  public FxWorkers(FxSettlementService fxSettlementService) {
    this.fxSettlementService = fxSettlementService;
  }

  /** autoComplete=false: one in five jobs is deliberately never completed,
   * simulating an external rate-feed outage -- the owning instance stays
   * ACTIVE indefinitely (the job keeps timing out and being redelivered,
   * but never resolves). This is what gives the report's "versions with
   * live instances" gap #4 signal real, currently-running instances on
   * v1/v2 rather than nothing, since without a genuine wait point every
   * fx-settlement instance completes in milliseconds of simulated time and
   * none are ever "live" by the time an assessment runs. Selection is by
   * job key modulo, not random, so retries of the same job land the same
   * way rather than eventually succeeding by chance. */
  @JobWorker(type = "lock-fx-rate", autoComplete = false)
  public void lockFxRate(JobClient client, ActivatedJob job) {
    if (job.getKey() % 5 == 0) {
      LOG.warn("Simulated rate-feed outage for job {} -- leaving unresolved", job.getKey());
      return;
    }
    String currencyPair = String.valueOf(job.getVariablesAsMap().get("currencyPair"));
    double rate = fxSettlementService.lockRate(currencyPair);
    client.newCompleteCommand(job).variables(Map.of("lockedRate", rate)).send();
  }

  @JobWorker(type = "settle-fx-leg")
  public Map<String, Object> settleFxLeg(final ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    String currencyPair = String.valueOf(vars.get("currencyPair"));
    double amount = ((Number) vars.getOrDefault("lockedRate", 1)).doubleValue();
    boolean settled = fxSettlementService.settleLeg(currencyPair, amount);
    return Map.of("settled", settled);
  }

  /** v2 addition. */
  @JobWorker(type = "confirm-fx-settlement")
  public Map<String, Object> confirmFxSettlement(final ActivatedJob job) {
    String currencyPair = String.valueOf(job.getVariablesAsMap().get("currencyPair"));
    boolean confirmed = fxSettlementService.confirmSettlement(currencyPair);
    return Map.of("settlementConfirmed", confirmed);
  }

  /** v3 addition. */
  @JobWorker(type = "reconcile-fx-ledger")
  public Map<String, Object> reconcileFxLedger(final ActivatedJob job) {
    String currencyPair = String.valueOf(job.getVariablesAsMap().get("currencyPair"));
    boolean reconciled = fxSettlementService.reconcileLedger(currencyPair);
    return Map.of("ledgerReconciled", reconciled);
  }
}
