package com.northwindbank.services;

import com.northwindbank.clients.HttpGateway;
import com.northwindbank.clients.LedgerRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Domain service for P16 (fx-settlement), v1/v2/v3. */
@Service
public class FxSettlementService {

  private static final Logger LOG = LoggerFactory.getLogger(FxSettlementService.class);

  private final HttpGateway httpGateway;
  private final LedgerRepository ledgerRepository;

  public FxSettlementService(HttpGateway httpGateway, LedgerRepository ledgerRepository) {
    this.httpGateway = httpGateway;
    this.ledgerRepository = ledgerRepository;
  }

  public double lockRate(String currencyPair) {
    LOG.info("Locking FX rate for {}", currencyPair);
    httpGateway.get("https://fx-rates.internal.northwindbank.example.com/v1/lock/" + currencyPair);
    return 1.0;
  }

  public boolean settleLeg(String currencyPair, double amount) {
    LOG.info("Settling {} {}", currencyPair, amount);
    return httpGateway.postJson(
        "https://fx-settlement.internal.northwindbank.example.com/v1/settle",
        java.util.Map.of("currencyPair", currencyPair, "amount", amount));
  }

  public boolean confirmSettlement(String currencyPair) {
    LOG.info("Confirming settlement for {}", currencyPair);
    return true;
  }

  public boolean reconcileLedger(String currencyPair) {
    return ledgerRepository.reconcile(currencyPair);
  }
}
