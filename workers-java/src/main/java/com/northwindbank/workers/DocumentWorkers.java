package com.northwindbank.workers;

import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Worker for P06 (document-collection)'s multi-instance chase step. Pure
 * -- state tracking only, no I/O sink. */
@Component
public class DocumentWorkers {

  private static final Logger LOG = LoggerFactory.getLogger(DocumentWorkers.class);

  @JobWorker(type = "chase-document")
  public Map<String, Object> chaseDocument(final ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    LOG.info("Chasing document {} for instance {}", vars.get("document"), job.getProcessInstanceKey());
    return Map.of("documentStatus", "chased");
  }
}
