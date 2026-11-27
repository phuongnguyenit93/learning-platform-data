# Authorization for Actuator in Spring Boot

Actuator provides health, metrics, and many endpoints for operations. These endpoints can disclose database state, internal topology, route names, application configuration, or diagnostic data. Therefore, exposing endpoints over HTTP must be paired with clear authorization: health probes should only read the required status, monitoring agents should be allowed to scrape metrics, and administrative endpoints should be restricted to operators with appropriate permissions.

In Spring Boot, authorization for Actuator is typically implemented using Spring Security combined with endpoint exposure and network controls. These three layers answer different questions: does the endpoint exist, is the endpoint exposed over the web, and which callers are allowed to access it. Configuring exposure alone does not create authentication; having roles in Security alone does not make an unexposed endpoint appear automatically.

The lesson **Authorization for Actuator** belongs to the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module. This module focuses on setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between endpoint availability, exposure, authentication, and authorization.
- Protect Actuator endpoints with Spring Security request matchers.
- Design separate permissions for health probes, metrics scraping, and operator endpoints.
- Understand the difference between a shared port and a separate management port.
- Configure health details according to access permissions.
- Avoid overly broad wildcard exposure or granting excessive administrative privileges.
- Test 401, 403, 404, and monitoring client behavior.
- Combine authorization with network isolation, TLS, and secret management.

## 2. Four Control Layers for Actuator

| Layer | Question | Mechanism |
| --- | --- | --- |
| Availability | Is the endpoint created in the application? | Actuator dependency, auto-configuration, endpoint conditions |
| Exposure | Which HTTP/JMX surface is the endpoint exposed on? | `management.endpoints.web.exposure` / JMX exposure |
| Authentication | How does the caller prove its identity? | Basic auth, OAuth2 resource server, mTLS, or appropriate identity |
| Authorization | Is the authenticated caller allowed to invoke this endpoint? | Spring Security roles/authorities and request matchers |

For example: having the Actuator dependency makes the health endpoint available; web exposure brings health onto HTTP; authentication identifies the monitoring identity; authorization allows that identity to call health. If one layer is not configured, the access outcome can differ.

## 3. Expose Only Necessary Endpoints

By default, do not assume every Actuator endpoint is exposed over HTTP. Configure an allow-list based on actual needs:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

The list above is an example for a service with health checks and metrics scraping. Do not include `env`, `configprops`, `beans`, `heapdump`, or `threaddump` in a public allow-list without evaluating the information they disclose and their operational cost.

Exposure does not replace security. If an endpoint is exposed without proper authentication/authorization, it can be accessed by any caller with a network route to the application.

### Endpoint-Specific Access

Actuator provides endpoint access controls in newer Spring Boot versions, allowing endpoints to be restricted to `none`/`read-only`/`unrestricted` depending on the feature/version. This serves as an additional control layer alongside exposure and Spring Security. Check the property metadata for your exact Spring Boot version; do not assume all versions support the same set of access levels.

## 4. Securing Actuator with Spring Security

Example policy for an application using a shared application port:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

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
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This is an example policy using a JWT resource server. The application must configure an appropriate issuer/JWK or JWT decoder and map authorities accordingly. If using Basic authentication, mTLS, or another service identity, replace the authentication mechanism to fit the environment.

### Request Matcher Order Matters

Spring Security applies matchers in declaration order. More specific rules should precede more general rules:

1. Health endpoints are accessed by probes according to policy.
2. The Prometheus endpoint requires a dedicated authority for the metrics scraper.
3. Remaining Actuator endpoints require an operator role.
4. Application routes enforce business authentication/authorization.

If you place the `/actuator/**` matcher before the Prometheus matcher, Prometheus requests may be handled by the `OPS` rule first and never reach the metrics-specific rule.

## 5. Health Probes and Health Details

Kubernetes or platform probes typically only need to know whether an instance is UP or DOWN. Probes generally do not need to read database hostnames, exception messages, or component details.

Example:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

Exact property names must match your Spring Boot version. With this configuration, health status can be returned to unauthorized callers, while details are shown only when the caller is authorized per policy. Verify the actual response and security chain.

Do not blindly permit all health subpaths. The `/actuator/health/**` rule may include health groups and component-specific paths. If subpaths return more details than intended, narrow the matchers or expose only the required group. One option is to create a dedicated health group for probes that returns only status and no internal details.

## 6. Metrics Scrapers and Operators Are Two Different Identities

A monitoring agent typically only needs to read metrics. An operator may need access to additional diagnostic endpoints. Using two separate authorities helps limit permissions:

| Identity | Appropriate Permissions | Should Not Be Granted by Default |
| --- | --- | --- |
| Kubernetes probe | Read required health status | `env`, `configprops`, `heapdump` |
| Prometheus scraper | Read `/actuator/prometheus` | Changing log levels or shutdown |
| Operations engineer | Approved diagnostic endpoints | All endpoints unrestricted |
| Application user | Business APIs per business role | Actuator management endpoints |

Even if the metrics endpoint is only reachable over an internal network, appropriate identity/service authentication should still be used. Network location alone does not prove a caller is trustworthy.

### Do Not Share Credentials Across All Monitoring Workloads

Separate credentials for scrapers and operators allow revoking or rotating one permission without impacting the entire system. Use a secret manager or workload identity; avoid hardcoding tokens in ConfigMaps, source control, Docker images, or log output.

## 7. Separate Management Port and Security Chains

When the management server runs on a separate port, a separate security policy can be applied depending on the Spring Boot/Spring Security configuration. This helps separate application and management routes, though you must inspect the actual request matchers and filter chains.

Example:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
```

Port 8081 still belongs to the same process in a typical setup. Firewalls, Kubernetes NetworkPolicies, or service routing should allow only probe/monitoring networks to reach the management port.

### Separate SecurityFilterChain

If configuring multiple `SecurityFilterChain` beans, you must choose an appropriate matcher for the management port and ensure chain order does not accidentally capture application traffic or bypass Actuator requests. How matching by management port/context works depends on the Spring Boot/Security version; check the built-in framework request matchers rather than relying on a client-controlled `Host` header.

Do not create a management chain with `permitAll` for the entire port if that port remains reachable from untrusted networks. Network isolation and authorization must coexist.

## 8. What Do 401, 403, and 404 Mean?

| HTTP Status | Common Interpretation | What to Check |
| --- | --- | --- |
| 401 Unauthorized | Caller is unauthenticated or credentials are invalid | Token, Basic credentials, issuer/JWK, certificate |
| 403 Forbidden | Caller is authenticated but lacks authority/role | Role mapping, matcher order, granted authorities |
| 404 Not Found | Endpoint does not exist, is not exposed, or path is wrong | Dependency, exposure, base path, management port |
| 200 OK | Request succeeded | Verify the response only contains data the caller is allowed to see |

A security configuration may intentionally return 404 instead of 403 to reduce endpoint disclosure. Therefore, check logs/security events and endpoint configuration before drawing conclusions.

## 9. CSRF, CORS, and Management Endpoints

CSRF and CORS solve different problems than authorization:

- CSRF protects certain browser-based authenticated requests from cross-site request forgery.
- CORS determines which origins' browser JavaScript may read responses from.
- Authentication/authorization determine who the caller is and what they are allowed to do.

A Prometheus scraper or Kubernetes probe is typically not a browser client. Do not disable CSRF application-wide just to scrape metrics; if you need to exempt CSRF for a machine-to-machine endpoint, scope the matcher specifically and evaluate the authentication mechanism.

CORS is not an access control for server-to-server callers. A non-browser client can call an endpoint regardless of CORS response headers.

## 10. Protecting Observability Information and Data

Actuator is not the only source that can leak data. Metrics, logs, traces, baggage, and health details all require policies:

| Signal | Risk | Control |
| --- | --- | --- |
| Health details | Hostnames, dependency state, exception details | Role-based `show-details`, minimal groups |
| Metrics | Route names, traffic patterns, internal topology | Authenticated scrape, network isolation |
| Logs | Tokens, SQL bind values, personal data | Redaction, structured logging, access control |
| Traces | Span attributes, baggage, URLs, and exception data | Attribute allow-list, sampling/retention, redaction |
| Environment/config endpoints | Secrets and configuration values | Do not expose publicly; minimal operator permissions |

Never log `Authorization` headers, cookies, passwords, API keys, or full request payloads into logs or traces. Avoid using user ID, email, order ID, or trace ID as metric tags due to cardinality and privacy risks.

## 11. TLS, Network Policy, and Secret Rotation

Application-layer authorization should be reinforced with transport and network controls:

1. Use HTTPS/TLS for management traffic crossing the network.
2. Restrict the management port with firewalls, security groups, or NetworkPolicies.
3. Publish the management Service internally only if the deployment platform supports it.
4. Use service identities or workload identities for scraper/operator automation.
5. Rotate credentials/certificates and revoke identities no longer in use.
6. Audit access to management endpoints per policy.

If using TLS termination at ingress, evaluate the hop from ingress to the application as well. If mTLS is required, validate the client certificate and map the identity to an authority; do not merely check for the presence of a self-declared header.

## 12. Testing Actuator Authorization

Do not only test that an endpoint returns 200 for an admin. Test each identity:

| Test Case | Caller | Expected Outcome |
| --- | --- | --- |
| Health probe | Probe identity/anonymous per policy | Only required status is readable |
| Metrics scrape | Metrics authority | Can read Prometheus endpoint |
| Metrics without role | Authenticated user without metrics scope | 403 or policy denial |
| Operator endpoint | OPS role | Only exposed and permitted endpoints |
| Anonymous operator access | No credentials | 401/403 |
| Application user | Business role | Does not automatically get Actuator access |
| Sensitive details | Unauthorized caller | Details hidden or request denied |
| Unknown endpoint | Any caller | 404 per endpoint availability/exposure |

### Integration Test Example

With Spring Security Test, you can test request authorization:

```java
@Test
void metricsRequiresMetricsAuthority() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_metrics.read")
            )))
        .andExpect(status().isOk());
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

This example requires Spring Security Test, MockMvc, and JWT test support to be configured. If the endpoint is not exposed, the result may be 404; tests should configure the Actuator endpoint in a real application context to verify the authorization layer.

## 13. Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Scraper receives 401 | Missing token/credentials or misconfigured authentication | Check workload identity, issuer, and credentials |
| Scraper receives 403 | Valid token but missing authority | Check scope/role mapping and matcher order |
| Endpoint returns 404 | Not exposed, missing dependency, or wrong management base path/port | Check endpoint availability and exposure |
| Health probe receives 401 | Probe endpoint requires authentication | Design probe identity or minimal access rule |
| Health details exposed to anonymous | `show-details` or security policy too broad | Restrict details and matchers |
| Operator blocked despite having role | Wrong authority prefix or matcher order | Check `ROLE_` prefix, scopes, and `SecurityFilterChain` |
| Application routes hit management rules | Multiple filter chains matching incorrectly | Check chain order and request matchers |
| Separate port still reachable from internet | Firewall/Service/NetworkPolicy too permissive | Narrow network routes and listener exposure |
| CORS enabled but endpoint still called | CORS does not block server-to-server requests | Use authentication/authorization |
| Token appears in logs | Logging interceptor writes headers | Redact `Authorization`/`Cookie` headers |
| TLS handshake fails | Wrong trust chain, hostname, or client cert | Check TLS/mTLS configuration |
| Old credential still works | Rotation/revocation incomplete | Check secret lifecycle and identity revocation |

### Pre-Production Review Checklist

1. List the endpoints that genuinely need to be exposed.
2. Define separate identities for probes, scrapers, and operators.
3. Place specific matchers before general matchers.
4. Verify health details do not leak sensitive topology or exceptions.
5. Protect the management port with TLS and network policy.
6. Test 401, 403, 404, and 200 for each caller type.
7. Verify logs do not record credentials or raw headers.
8. Confirm secret rotation, auditing, and revocation processes.

## 14. Practice: Authorizing Actuator for Three Caller Groups

**Context:** `order-service` exposes health, metrics, and Prometheus. Kubernetes needs health status; Prometheus needs to scrape metrics; operators need permission to view approved diagnostic endpoints.

### Part A — Policy Design

1. Expose `health`, `metrics`, and `prometheus`; do not enable wildcards.
2. Allow probes to read minimal health status.
3. Grant `SCOPE_metrics.read` authority to the scraper.
4. Grant the `OPS` role to operators via the identity provider.
5. Configure health details to appear only when authorized.
6. Restrict the management port to the internal network.

### Part B — Verification

| Case | Caller | Expected Observation |
| --- | --- | --- |
| A — Probe | Kubelet/probe identity | Can read readiness/liveness status |
| B — Scraper | Metrics scope | Can read `/actuator/prometheus` |
| C — Regular user | `ROLE_USER` | Cannot read metrics/operator endpoints |
| D — Operator | `OPS` role | Can only read permitted endpoints |
| E — Anonymous | No credentials | Cannot access diagnostics |
| F — Details | Insufficiently privileged caller | Health details hidden |
| G — Network | Caller outside internal network | Management port unreachable |
| H — Rotation | Revoke old token, issue new token | Old credential is rejected |

### Part C — Self-Assessment Questions

1. How does endpoint availability differ from exposure and authorization?
2. Why does exposing metrics not mean the endpoint is protected?
3. Why must specific matchers come before `/actuator/**`?
4. What distinct permissions should probes, scrapers, and operators have?
5. How does 401 differ from 403 and 404?
6. Why can health status be public while health details must be restricted?
7. Does CORS replace authentication for a Prometheus scraper?
8. When using a separate management port, what additional network controls are needed?
9. What observability data can contain PII/secrets?
10. How do you test credential rotation and revoked permissions?

## 15. Takeaways

**Authorization for Actuator** requires combining endpoint availability, exposure, authentication, and authorization. Spring Boot Actuator determines which endpoints are present; exposure brings endpoints onto HTTP/JMX; Spring Security authenticates callers and checks authorities/roles. Network isolation and TLS add protection layers for management traffic.

Design separate permissions for health probes, metrics scrapers, and operators. Expose only necessary endpoints, place specific matchers before general matchers, and gate health details by permission. Test all outcomes—200, 401, 403, and 404—and never treat CORS or a separate port as authorization. Protect credentials, redact logs/traces, and bound metric dimensions to avoid leaking PII, secrets, or topology. Policies tested per identity ensure observability endpoints support operations without granting excessive administrative privileges.
