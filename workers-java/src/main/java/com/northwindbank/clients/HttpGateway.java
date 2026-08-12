package com.northwindbank.clients;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Shared outbound-HTTP helper -- the third layer beneath a worker (worker ->
 * domain service -> this), giving the code analyzer's call-graph extraction
 * real depth to walk. Stubbed (logs and returns deterministically) since the
 * reference app has no real external bureau/rail/rate endpoint to call; the
 * point is the call-graph shape, not live integration.
 */
@Component
public class HttpGateway {

  private static final Logger LOG = LoggerFactory.getLogger(HttpGateway.class);

  public boolean postJson(String url, Object payload) {
    LOG.info("POST {} payload={}", url, payload);
    return true;
  }

  public String get(String url) {
    LOG.info("GET {}", url);
    return "{}";
  }
}
