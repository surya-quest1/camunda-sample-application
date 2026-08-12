package com.northwindbank.workers;

import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Workers for P07 (underwriting-review)'s SLA side paths. Both pure --
 * classification bookkeeping only, no I/O sink. */
@Component
public class UnderwritingWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(UnderwritingWorkers.class);

  @JobWorker(type = "escalate-sla-breach")
  public Map<String, Object> escalateSlaBreach(final ActivatedJob job) {
    LOG.info("Escalating SLA breach for instance {}", job.getProcessInstanceKey());
    return Map.of("slaBreachSeverity", "high");
  }

  @JobWorker(type = "handle-case-sla-breach")
  public Map<String, Object> handleCaseSlaBreach(final ActivatedJob job) {
    LOG.info("Handling case SLA breach for instance {}", job.getProcessInstanceKey());
    return Map.of("caseSlaBreachHandled", true);
  }
}
