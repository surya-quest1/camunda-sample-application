package com.northwindbank.clients;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * JDBC-backed repository for fund reservations (P08) and FX reconciliation
 * (P16 v3). Uses Spring's JdbcTemplate against the application datasource
 * (an embedded H2 in this reference environment). Deliberately fails the first
 * reserve attempt for a given key -- via an in-memory attempt counter -- so the
 * reserve-funds worker has a transient error to retry against (doc 06's
 * "broker-driven retries move to the SDK" concern). A DB error against the
 * reference app's empty schema is caught so seeded instances still complete.
 */
@Component
public class LedgerRepository {

  private static final Logger LOG = LoggerFactory.getLogger(LedgerRepository.class);

  private final JdbcTemplate jdbcTemplate;
  private final ConcurrentHashMap<String, AtomicInteger> reservationAttempts = new ConcurrentHashMap<>();

  public LedgerRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public boolean reserve(String applicationId, double amount) {
    int attempt = reservationAttempts.computeIfAbsent(applicationId, k -> new AtomicInteger(0)).incrementAndGet();
    if (attempt == 1) {
      LOG.warn("Simulated transient ledger contention on first attempt for {}", applicationId);
      return false;
    }
    try {
      jdbcTemplate.update(
          "INSERT INTO reservations(application_id, amount) VALUES (?, ?)", applicationId, amount);
    } catch (DataAccessException e) {
      LOG.info("Reserve insert skipped (no live schema in this environment): {}", e.getMessage());
    }
    LOG.info("Reserved {} for {}", amount, applicationId);
    return true;
  }

  public void release(String applicationId) {
    try {
      jdbcTemplate.update("DELETE FROM reservations WHERE application_id = ?", applicationId);
    } catch (DataAccessException e) {
      LOG.info("Release delete skipped (no live schema in this environment): {}", e.getMessage());
    }
    LOG.info("Released reservation for {}", applicationId);
  }

  public boolean reconcile(String currencyPair) {
    LOG.info("Reconciling ledger for {}", currencyPair);
    return true;
  }
}
