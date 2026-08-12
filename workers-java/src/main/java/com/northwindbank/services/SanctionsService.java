package com.northwindbank.services;

import com.northwindbank.clients.HttpGateway;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P04 (sanctions-screening) -- the Java side of the
 * screen/re-screen pair (rescreen-sanctions-pep lives in workers-python). */
@Service
public class SanctionsService {

  private static final Logger LOG = LoggerFactory.getLogger(SanctionsService.class);

  private final HttpGateway httpGateway;

  public SanctionsService(HttpGateway httpGateway) {
    this.httpGateway = httpGateway;
  }

  public boolean screen(String applicantRef) {
    LOG.info("Screening {} against sanctions/PEP lists", applicantRef);
    return httpGateway.postJson(
        "https://sanctions-screening.internal.northwindbank.example.com/v1/screen",
        java.util.Map.of("applicantRef", applicantRef));
  }
}
