package com.northwindbank.services;

import com.northwindbank.clients.CoreBankingClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P05 (credit-bureau-assessment). */
@Service
public class CreditBureauService {

  private static final Logger LOG = LoggerFactory.getLogger(CreditBureauService.class);

  private final CoreBankingClient coreBankingClient;

  public CreditBureauService(CoreBankingClient coreBankingClient) {
    this.coreBankingClient = coreBankingClient;
  }

  public boolean postToCoreBanking(String applicationId, double requestedAmount) {
    LOG.info("Posting credit assessment to core banking for {}", applicationId);
  return coreBankingClient.postLedgerAdjustment(applicationId, requestedAmount);
  }
}
