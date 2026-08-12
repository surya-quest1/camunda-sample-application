package com.northwindbank.clients;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * JDBC-shaped repository stub for fund reservations (P08) and FX
 * reconciliation (P16 v3) -- an in-memory map standing in for a real ledger
 * database. Deliberately allows a transient failure the first time a given
 * key is reserved, so the reserve-funds worker has something to retry
 * against (doc 06's "broker-driven retries move to the SDK" concern).
 */
@Component
public class LedgerRepository {

  private static final Logger LOG = LoggerFactory.getLogger(LedgerRepository.class);

  private final ConcurrentHashMap<String, Double> reservations = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<String, AtomicInteger> reservationAttempts = new ConcurrentHashMap<>();

  public boolean reserve(String applicationId, double amount) {
    int attempt = reservationAttempts.computeIfAbsent(applicationId, k -> new AtomicInteger(0)).incrementAndGet();
    if (attempt == 1) {
      LOG.warn("Simulated transient ledger contention on first attempt for {}", applicationId);
      return false;
    }
    reservations.put(applicationId, amount);
    LOG.info("Reserved {} for {}", amount, applicationId);
    return true;
  }

  public void release(String applicationId) {
    reservations.remove(applicationId);
    LOG.info("Released reservation for {}", applicationId);
  }

  public boolean reconcile(String currencyPair) {
    LOG.info("Reconciling ledger for {}", currencyPair);
    return true;
  }
}
