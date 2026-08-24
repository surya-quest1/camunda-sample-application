package com.northwindbank.clients;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

/**
 * Shared outbound-HTTP helper -- the third layer beneath a worker (worker ->
 * domain service -> this). Uses Spring's RestTemplate for real outbound calls.
 * Since the reference app has no live external bureau/rail/rate endpoint, a
 * connection failure to a fictional internal host is caught and a deterministic
 * result returned so seeded instances still complete -- the real I/O sink and
 * the call-graph shape are what matter here, not live integration.
 */
@Component
public class HttpGateway {

  private static final Logger LOG = LoggerFactory.getLogger(HttpGateway.class);

  private final RestTemplate restTemplate = new RestTemplate();

  public boolean postJson(String url, Object payload) {
    LOG.info("POST {} payload={}", url, payload);
    try {
      restTemplate.postForObject(url, payload, String.class);
      return true;
    } catch (RestClientException e) {
      LOG.info("POST {} (no live endpoint in this environment): {}", url, e.getMessage());
      return true;
    }
  }

  public String get(String url) {
    LOG.info("GET {}", url);
    try {
      String body = restTemplate.getForObject(url, String.class);
      return body != null ? body : "{}";
    } catch (RestClientException e) {
      LOG.info("GET {} (no live endpoint in this environment): {}", url, e.getMessage());
      return "{}";
    }
  }
}
