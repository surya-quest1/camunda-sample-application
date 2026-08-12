package com.northwindbank.services;

import com.northwindbank.clients.HttpGateway;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P13 (regulatory-reporting-batch). */
@Service
public class RegulatoryReportingService {

  private static final Logger LOG = LoggerFactory.getLogger(RegulatoryReportingService.class);

  private final HttpGateway httpGateway;

  public RegulatoryReportingService(HttpGateway httpGateway) {
    this.httpGateway = httpGateway;
  }

  public boolean buildDataset(String reportingPeriod) {
    LOG.info("Building regulatory dataset for period {}", reportingPeriod);
    return httpGateway.postJson(
        "https://regulatory-reporting.internal.northwindbank.example.com/v1/datasets",
        java.util.Map.of("reportingPeriod", reportingPeriod));
  }
}
