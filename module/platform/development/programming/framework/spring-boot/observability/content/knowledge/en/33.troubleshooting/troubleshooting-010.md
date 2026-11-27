# Actuator Endpoint Returning 401

A monitoring agent calls `/actuator/prometheus` and receives HTTP 401 Unauthorized. The application still processes business APIs normally, health probes may still run, while metrics dashboards start showing gaps. This situation typically involves authentication: the request has no credentials, credentials are expired/wrong, the token is rejected, or the request hits an unexpected security chain.

HTTP 401 indicates the server requires authentication or rejected the credentials sent. It differs from HTTP 403, which normally means the caller is authenticated but lacks permission. However, security configuration can intentionally hide endpoints with 404; therefore, inspect the response, security logs, endpoint exposure, and routing rather than concluding from the status code alone.

This lesson, **Actuator Endpoint Returning 401**, belongs to the **Troubleshooting** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module focuses on setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the meaning of HTTP 401 and distinguish it from 403/404.
- Identify the authentication mechanism protecting Actuator endpoints.
- Inspect Spring Security filter chains and matcher ordering.
- Diagnose credentials, JWT scopes, Basic authentication, and service identities.
- Distinguish the application port from the management port during investigation.
- Handle health probes and Prometheus scrapers with dedicated identities.
- Inspect CSRF, proxy headers, and TLS when relevant to the request.
- Use logs, `curl`, and integration tests to confirm the root cause.

## 2. What Does 401 Mean?

HTTP 401 Unauthorized normally occurs when a request is unauthenticated or its credentials are invalid. The server may return a `WWW-Authenticate` header indicating the required authentication scheme.

| Status | Common Meaning | Example |
| --- | --- | --- |
| 200 | Request accepted and processed | Scraper reads metrics |
| 401 | Unauthenticated or invalid credentials | Missing bearer token or wrong Basic credentials |
| 403 | Authenticated but insufficient permissions | Valid token lacking `SCOPE_metrics.read` |
| 404 | Endpoint does not exist, is not exposed, or is hidden | Wrong Actuator path or unexposed endpoint |
| 503 | Service/endpoint unavailable per response policy | Health endpoint reports unavailable status |

Do not switch everything causing 401 to `permitAll()` just to make dashboards work. First identify who the caller is, what permissions the endpoint requires, and which filter chain handles the request.

## 3. Confirm the Right Endpoint and Port

Before investigating authentication, verify the request reaches the intended management endpoint:

- Is Actuator present in application dependencies?
- Is the endpoint exposed over the web?
- Is the base path `/actuator` or changed to `/manage`?
- Does the management server share the application port or run on a separate port?
- Does the request pass through an ingress, gateway, or service mesh?

Example when application and management server share a port:

```text
Application API:  http://localhost:8080/api/orders
Actuator:         http://localhost:8080/actuator/health
Prometheus:       http://localhost:8080/actuator/prometheus
```

Example when management server runs on a separate port:

```text
Application API:  http://localhost:8080/api/orders
Actuator:         http://localhost:8081/actuator/health
Prometheus:       http://localhost:8081/actuator/prometheus
```

Calling the wrong port can yield a response from a different server or security policy. Check Kubernetes Service `targetPort`, container ports, and Prometheus scrape targets.

## 4. Check Endpoint Exposure

An endpoint must be enabled and exposed before callers can access it via HTTP. Allowlist example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Exposure does not grant access authorization; it only puts the endpoint on the web surface. If an endpoint is not exposed, the result is usually 404. If the endpoint is exposed yet Security requires authentication, requests without credentials can receive 401.

During investigation, inspect the runtime configuration of the actual profile and deployment. Do not assume a local YAML file represents production configuration.

## 5. Inspect the Spring Security Filter Chain

When Spring Security is present, Actuator requests are processed by one or more `SecurityFilterChain` instances. Check:

1. Which chain matches the request path/management context?
2. Does a broad matcher such as `/**` or `/actuator/**` appear before the intended chain?
3. Which authentication mechanism is enabled: Basic, JWT resource server, session, or mTLS?
4. Do request matchers use the right base path and port/context?
5. Is a custom authentication entry point returning 401?

Illustrative same-port policy using a JWT resource server:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers("/actuator/health/**").permitAll()
            .requestMatchers("/actuator/prometheus")
                .hasAuthority("SCOPE_metrics.read")
            .requestMatchers("/actuator/**").hasRole("OPS")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}
```

This is an illustrative example; DSL syntax can vary by Spring Security version. The application must configure a JWT decoder/issuer and authority mapping. Specific matchers must precede general matchers. If `/actuator/**` is placed before the Prometheus rule, requests may be evaluated against the `OPS` rule first.

### Why Do Valid Requests Still Receive 401?

Common causes:

- `Authorization` header was not sent or was stripped by a proxy.
- Token expired, or has wrong issuer, audience, or signature.
- Basic credentials are wrong or rotated while the scraper still uses the old secret.
- JWT authenticated, yet a custom entry point or different filter chain handled the request.
- Scraper calls the management port while credentials were only configured for the application route.
- Identity provider/JWK endpoint is unreachable so the token cannot be verified.

If the token was authenticated yet lacks the required role/scope, the response is typically 403. Inspect security logs to separate authentication failure from authorization denial.

## 6. Test Credentials from the Exact Caller

Test the request directly from an environment matching the scraper:

```bash
curl -i http://localhost:8081/actuator/prometheus
```

If the endpoint requires a bearer token:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8081/actuator/prometheus
```

If using HTTP Basic:

```bash
curl -i -u "$METRICS_USER:$METRICS_PASSWORD" \
  http://localhost:8081/actuator/prometheus
```

Never paste real tokens/passwords into tickets, shared terminal logs, or chat. Use test secrets, secure environment variables, or workload identities. Run tests from a pod/host sharing the same network path as Prometheus to rule out differences in DNS, proxies, and service routing.

### Inspecting Response Headers

```bash
curl -sS -D - -o /dev/null \
  http://localhost:8081/actuator/prometheus
```

Observe status, `WWW-Authenticate`, `Location` if redirected, `Server`, and correlation request IDs. Do not conclude from the `Server` header alone; a proxy can rewrite response headers.

## 7. Health Probes and Prometheus Scrapers Have Different Needs

Do not share one policy for every caller:

| Caller | Need | Suggested Policy |
| --- | --- | --- |
| Kubernetes probe | Read required health status | Allow only the exact health path or use a probe identity |
| Prometheus scraper | Read metrics exposition | Dedicated token/scope or mTLS |
| Operator | Access approved diagnostics | `OPS` role or equivalent authority |
| Application user | Business API | No automatic Actuator access |

For instance, health status can be readable while details are restricted to authorized callers:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

Properties and response behavior depend on Spring Boot version/security setup. Check health group paths, base path, and security matchers. Do not `permitAll` on all Actuator subpaths just to make Kubernetes probes pass.

## 8. Separate Management Port and Multiple SecurityFilterChains

When configured as:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
```

Management endpoints may run under a separate management web context/server. How security chains and matchers apply depends on the Spring Boot/Spring Security version and application setup. Check request matchers intended for the management server if supported by your version; avoid relying on the `Host` header since callers can spoof it.

A common mistake is the application API security chain requiring JWT while probes calling the management port send no token. Another mistake is a dedicated chain meant for the management context having a wrong matcher, causing requests to fall through to another chain.

Network policies must still restrict the management port. A separate port does not automatically authenticate callers or make an endpoint secure.

## 9. CSRF, CORS, Proxies, and TLS

### CSRF and CORS

Prometheus scrapers and Kubernetes probes are typically machine-to-machine clients, not browsers. CORS does not block server-to-server requests and does not replace authentication. CSRF mainly applies to browser-based authenticated requests; do not disable CSRF application-wide just to fix a scrape error.

If a security chain enables CSRF and an endpoint uses a state-changing method, 403 may occur due to a missing CSRF token. For a `GET` scrape endpoint, 401 usually points to authentication; inspect the response and security logs to confirm.

### Reverse Proxies and the Authorization Header

An ingress/gateway may strip or overwrite the `Authorization` header, route to the wrong upstream, or apply its own auth middleware. Compare requests across client, gateway, and application logs without logging token values. Check proxy configuration to preserve required headers and avoid forwarding credentials to untrusted upstreams.

### TLS and mTLS

If using mTLS, the server may require a client certificate. An expired certificate, one outside the trust chain, or one not mapped to an identity can cause authentication failure. Check certificate chains, SANs, expiry, truststores, and client identity mapping. With bearer tokens, TLS is still required to protect tokens in transit.

## 10. Ordered Investigation Workflow

Follow these steps to narrow down the cause:

1. **Record the request:** URL, port, method, timestamp, source identity, and status; do not store secrets.
2. **Confirm the endpoint:** Actuator dependency, exposure, base path, and management port.
3. **Test from the same network:** call the endpoint from a pod/host similar to the scraper.
4. **Check authentication:** was the header sent, is the token unexpired, and are issuer/audience/signature valid?
5. **Check filter chains:** which matcher hits, in what chain order, and which entry point produces 401?
6. **Check authorization:** does the caller have the required authority/role? If authenticated yet lacking permissions, the response is usually 403.
7. **Check intermediaries:** ingress, service mesh, reverse proxy, TLS/mTLS, and header forwarding.
8. **Verify recovery:** after fixing, confirm the scraper scrapes successfully and time series resume updating.

### Logs to Look For

Depending on logging level and Security version, look for authentication entry point/provider failures, JWT decoder/issuer/JWK validation errors, authority mapping/authorization decisions, request path/selected filter chain, and proxy upstream/TLS errors.

Only enable debug logging temporarily in an appropriate environment. Security debug logs can contain sensitive metadata; do not leave them on indefinitely in production without review.

## 11. Testing to Prevent Recurrence

Integration tests should verify both valid and invalid callers:

```java
@Test
void metricsEndpointAcceptsMetricsAuthority() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_metrics.read")
            )))
        .andExpect(status().isOk());
}

@Test
void metricsEndpointRejectsAnonymousCaller() throws Exception {
    mockMvc.perform(get("/actuator/prometheus"))
        .andExpect(status().isUnauthorized());
}

@Test
void ordinaryUserCannotReadMetrics() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_USER")
            )))
        .andExpect(status().isForbidden());
}
```

This example requires Spring Security Test, MockMvc, and JWT test support. A 404 can occur if the endpoint is unexposed or the management path differs; integration test configuration must match the real application context.

Beyond controller/security tests, test scraping end-to-end from Prometheus or a test client on the same network. Confirm the scrape target is `UP`, sample timestamps keep advancing, and dashboard gaps disappear.

## 12. Troubleshooting

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Prometheus receives 401 | Missing token or scraper lacks configured credentials | Scrape auth config and secret reference |
| Token looks valid yet still 401 | Expired, wrong issuer/audience/signature, or JWK unavailable | Decoder logs and identity provider |
| Health probe receives 401 | Health path is protected by authentication | Add minimal probe rule/identity |
| Prometheus receives 403 | Authenticated but missing metrics scope | Granted authorities and matchers |
| Endpoint returns 404 | Wrong port/base path or not exposed | Actuator exposure and management config |
| Local `curl` works, scraper fails | Different secret, DNS, proxy, or network path | Test from scraper pod and compare request path |
| `Authorization` header lost after ingress | Proxy does not forward header | Gateway/ingress policy |
| Only management port fails | Wrong management security chain/address/port mapping | Management context and service `targetPort` |
| Basic auth stops working after rotation | Scraper still uses old secret | Update secret and verify rollout |
| mTLS handshake fails | Expired certificate or wrong trust chain | Client/server certificates and truststore |
| CSRF returns 403 | Request blocked by CSRF protection | Method, CSRF matcher, and security logs |
| Scrape succeeds yet dashboard stays empty | Wrong query/labels or scrape interval | Raw series and Prometheus Targets |

### Post-Fix Checklist

1. Requests from the right scraper identity return 200.
2. Callers without credentials receive the expected status per policy.
3. Authenticated callers lacking roles receive 403.
4. Health probes read only minimal data.
5. Management endpoints remain restricted to the intended network.
6. Prometheus target transitions to `UP` and new scrape samples appear.
7. No credentials/tokens appear in logs or test output.

## 13. Practice: Fixing a Prometheus Scrape Receiving 401

**Context:** `order-service` exposes `/actuator/prometheus` on management port `8081`. After a secret rotation, the Prometheus target switches to `DOWN` with HTTP 401. The application API on port `8080` keeps working.

### Part A — Gathering Evidence

1. Record the scrape failure timestamp and target URL.
2. Confirm port `8081` and path `/actuator/prometheus`.
3. Check which secret reference the scrape configuration uses.
4. Check application security logs and the authentication failure reason.
5. Verify whether any proxy/service forwards the `Authorization` header.

### Part B — Remediation and Verification

1. Update the scraper to the new credential via the secret manager.
2. Verify the token/identity has the matching `metrics-read` authority.
3. Confirm the management server's filter chain matches the request properly.
4. Call the endpoint from a test environment using the same identity.
5. Verify the Prometheus target turns `UP` and new samples are ingested.
6. Revoke the old credential once rollout completes.

### Part C — Self-Assessment Questions

1. At which stage of the security flow does HTTP 401 differ from 403?
2. Why does a working application API not prove the management endpoint works?
3. How do you determine which `SecurityFilterChain` a request enters?
4. For what reasons can a JWT be rejected even with a valid signature?
5. Why should a Prometheus scraper have its own dedicated identity?
6. When does 404 indicate an unexposed endpoint?
7. Does CORS resolve a scraper's 401 error?
8. How can a reverse proxy break authentication?
9. Which logs help separate authentication failures from authorization denials?
10. How do you prove the issue is fixed end-to-end?

## 14. Key Takeaways

**Actuator endpoint returning 401** is usually an authentication issue: missing, wrong, or expired credentials, or the request entering an unexpected security chain. Confirm the right endpoint, port, base path, and exposure first; then inspect caller identity, `Authorization` headers, token validation, filter chains, and proxies/TLS. Distinguish 401 from 403 to tell whether the failure lies in authentication or authority mapping.

Design dedicated permissions for health probes, Prometheus scrapers, and operators. Use securely managed credentials/workload identities, never log tokens, and never open `permitAll()` across all of Actuator just to fix scraping. Test 200/401/403 cases and verify scraping from the actual network path. After fixing, verify the target is `UP`, new samples are ingested, and dashboards resume updating. An evidence-based workflow restores telemetry while keeping management endpoints protected.
