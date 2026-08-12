package com.northwindbank.services;

import com.northwindbank.clients.HttpGateway;
import com.northwindbank.clients.LedgerRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P08 (fund-disbursement). */
@Service
public class DisbursementService {

  private static final Logger LOG = LoggerFactory.getLogger(DisbursementService.class);

  private final LedgerRepository ledgerRepository;
  private final HttpGateway httpGateway;

  public DisbursementService(LedgerRepository ledgerRepository, HttpGateway httpGateway) {
    this.ledgerRepository = ledgerRepository;
    this.httpGateway = httpGateway;
  }

  public boolean reserveFunds(String applicationId, double amount) {
    return ledgerRepository.reserve(applicationId, amount);
  }

  public void releaseReservation(String applicationId) {
    ledgerRepository.release(applicationId);
  }

  public void notifyLedgerPosted(String applicationId) {
    LOG.info("Notifying ledger posted for {}", applicationId);
    httpGateway.postJson(
        "https://ledger.internal.northwindbank.example.com/v1/events/posted",
        java.util.Map.of("applicationId", applicationId));
  }
}
