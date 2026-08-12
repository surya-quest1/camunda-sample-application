package com.northwindbank.services;

import com.northwindbank.clients.HttpGateway;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P03 (identity-verification). */
@Service
public class IdentityBureauService {

  private static final Logger LOG = LoggerFactory.getLogger(IdentityBureauService.class);

  private final HttpGateway httpGateway;

  public IdentityBureauService(HttpGateway httpGateway) {
    this.httpGateway = httpGateway;
  }

  /** Returns "verified" or "unverifiable". Throws BureauUnavailableException
   * on a simulated bureau outage. */
  public String checkBureau(String applicantRef) {
    String response =
        httpGateway.get(
            "https://identity-bureau.internal.northwindbank.example.com/v1/check/" + applicantRef);
    if (response == null) {
      throw new BureauUnavailableException("Identity bureau unreachable for " + applicantRef);
    }
    LOG.info("Bureau check for {} returned {}", applicantRef, response);
    return "verified";
  }

  public void recordSupplementaryEvidence(String applicantRef, String evidenceRef) {
    LOG.info("Recording supplementary evidence {} for {}", evidenceRef, applicantRef);
    httpGateway.postJson(
        "https://identity-bureau.internal.northwindbank.example.com/v1/evidence",
        java.util.Map.of("applicantRef", applicantRef, "evidenceRef", evidenceRef));
  }

  public static class BureauUnavailableException extends RuntimeException {
    public BureauUnavailableException(String message) {
      super(message);
    }
  }
}
