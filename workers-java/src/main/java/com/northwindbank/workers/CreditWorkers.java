package com.northwindbank.workers;

import com.northwindbank.services.CreditBureauService;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.spring.client.annotation.JobWorker;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Worker for P05 (credit-bureau-assessment). */
@Component
public class CreditWorkers {

  private final CreditBureauService creditBureauService;

  public CreditWorkers(CreditBureauService creditBureauService) {
    this.creditBureauService = creditBureauService;
  }

  @JobWorker(type = "core-banking-api-call")
  public Map<String, Object> coreBankingApiCall(final ActivatedJob job) {
    Map<String, Object> vars = job.getVariablesAsMap();
    String applicationId = String.valueOf(vars.get("applicationId"));
    double amount = ((Number) vars.getOrDefault("requestedAmount", 0)).doubleValue();
    boolean posted = creditBureauService.postToCoreBanking(applicationId, amount);
    return Map.of("coreBankingPosted", posted);
  }
}
