package com.northwindbank.workers;

import com.northwindbank.services.FxSettlementService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * DELIBERATE RECONCILIATION DEFECT (planted, not a bug in this codebase):
 * this worker registers for job type "legacy-fx-reconcile", which no BPMN
 * process in the estate references. It's a leftover from a prior manual
 * reconciliation flow, still deployed and still polling -- exactly the
 * "observedOnly" half of the reconciliation pair the code analyzer's
 * BPMN-vs-code cross-check is meant to catch. Its counterpart, the
 * "declaredOnly" defect, is job type "manual-ledger-adjustment" in P08
 * (fund-disbursement), which no worker in this codebase implements.
 */
@Component
public class LegacyWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(LegacyWorkers.class);

  private final FxSettlementService fxSettlementService;

  public LegacyWorkers(FxSettlementService fxSettlementService) {
    this.fxSettlementService = fxSettlementService;
  }

  @JobWorker(type = "legacy-fx-reconcile")
  public void legacyFxReconcile(final ActivatedJob job) {
    LOG.warn("legacy-fx-reconcile invoked -- this job type has no BPMN reference in the estate");
    fxSettlementService.reconcileLedger(String.valueOf(job.getVariablesAsMap().get("currencyPair")));
  }
}
