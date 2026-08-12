package com.northwindbank.workers;

import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P01's (loan-application) event-subprocess and boundary-event
 * side paths. Both pure -- no I/O sink, just bookkeeping -- rule-classified
 * read-only by the code analyzer without escalation. */
@Component
public class LoanLifecycleWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(LoanLifecycleWorkers.class);

  @JobWorker(type = "process-withdrawal")
  public Map<String, Object> processWithdrawal(final ActivatedJob job) {
    LOG.info("Processing withdrawal for process instance {}", job.getProcessInstanceKey());
    return Map.of("withdrawalProcessed", true);
  }

  @JobWorker(type = "process-cancellation")
  public Map<String, Object> processCancellation(final ActivatedJob job) {
    LOG.info("Processing cancellation for process instance {}", job.getProcessInstanceKey());
    return Map.of("cancellationProcessed", true);
  }
}
