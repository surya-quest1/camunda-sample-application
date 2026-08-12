package com.northwindbank.workers;

import com.northwindbank.services.RegulatoryReportingService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P13 (regulatory-reporting-batch)'s job-worker-side steps
 * (the in-broker FEEL script task and in-broker DMN task have no worker --
 * they run inside the engine). */
@Component
public class BatchWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(BatchWorkers.class);

  private final RegulatoryReportingService regulatoryReportingService;

  public BatchWorkers(RegulatoryReportingService regulatoryReportingService) {
    this.regulatoryReportingService = regulatoryReportingService;
  }

  @JobWorker(type = "build-regulatory-dataset")
  public Map<String, Object> buildRegulatoryDataset(final ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    boolean built = regulatoryReportingService.buildDataset(String.valueOf(vars.get("reportingPeriod")));
    return Map.of("datasetBuilt", built);
  }

  /** Pure -- classification logic only, no I/O sink. */
  @JobWorker(type = "classify-transactions-dmn")
  public Map<String, Object> classifyTransactions(final ActivatedJob job) {
    LOG.info("Classifying transactions for instance {}", job.getProcessInstanceKey());
    return Map.of("transactionsClassified", true);
  }
}
