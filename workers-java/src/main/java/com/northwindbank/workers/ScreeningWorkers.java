package com.northwindbank.workers;

import com.northwindbank.services.SanctionsService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Worker for P04 (sanctions-screening). Re-screen (rescreen-sanctions-pep)
 * is implemented in workers-python -- see PYTHON_DIALECT_NOTE.md. */
@Component
public class ScreeningWorkers {

  private final SanctionsService sanctionsService;

  public ScreeningWorkers(SanctionsService sanctionsService) {
    this.sanctionsService = sanctionsService;
  }

  @JobWorker(type = "screen-sanctions-pep")
  public Map<String, Object> screenSanctionsPep(final ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    boolean clear = sanctionsService.screen(String.valueOf(vars.get("applicantRef")));
    return Map.of("sanctionsClear", clear);
  }
}
