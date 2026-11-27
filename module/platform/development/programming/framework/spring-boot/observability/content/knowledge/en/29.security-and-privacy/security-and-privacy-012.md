# Verifying Metrics Read Permissions in Spring Boot

> **Chapter:** Security and Privacy  
> **Lesson:** Verifying Metrics Read Permissions  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Verify Metrics Read Permissions?

Metrics are often viewed as purely operational data, yet they can reveal topology, internal service names, routes, dependencies, traffic patterns, error states, and system capacity. A metrics endpoint open to any caller can help outsiders infer application structure or detect when the system is experiencing an outage.

**Verifying metrics read permissions** means confirming that only authorized identities and network paths can access metrics data. This spans multiple layers: listener/network exposure, TLS, authentication, authorization, endpoint exposure, and data policy.

A successful scrape must satisfy all of these simultaneously:
- The scraper can connect to the management listener.
- TLS and peer identity are verified when using HTTPS/mTLS.
- The scraper authenticates using the chosen mechanism.
- The identity holds permission to read the exact endpoint.
- The endpoint is exposed and the registry/exporter exists.
- The response does not disclose data outside the permitted scope.

~~~mermaid
flowchart TD
  A["Prometheus / scraper"] --> B["Network policy / firewall"]
  B --> C["TLS listener"]
  C --> D["Authentication"]
  D --> E["Authorization"]
  E --> F["Actuator endpoint exposure"]
  F --> G["Prometheus registry"]
  G --> H["Metrics response"]
~~~

HTTP 200 only proves that specific request was accepted. It does not prove the overall policy is secure. You must test valid callers, invalid callers, and alternate access paths such as public ingress or JMX.

## 2. Exposure Differs From Authentication and Authorization

These concepts solve different problems:

| Layer | Question | Example |
| --- | --- | --- |
| Exposure | Is the endpoint published over web/JMX? | Expose `prometheus` |
| Authentication | Who is the caller? | Basic credentials, client certificate, token |
| Authorization | What is the caller allowed to do? | Role `MONITORING` can GET metrics |
| Network reachability | Can the caller reach the listener? | Private subnet, NetworkPolicy |
| TLS | Are the connection and peer protected/verified? | HTTPS, mutual TLS |

Configuring exposure does not automatically create authentication or authorization. Conversely, an endpoint not exposed over the web may still be exposed via JMX if JMX is configured separately.

An exposed endpoint rejected by Spring Security still cannot be read. An endpoint with authentication whose listener is public and unrestricted on the network can still be scanned or brute-forced.

## 3. Expose Only Necessary Endpoints

With the Prometheus registry, the commonly used endpoint is `/actuator/prometheus`. Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Expose only `health` and `prometheus` if that is what the application needs. Never add `env`, `configprops`, `heapdump`, `threaddump`, `logfile`, or `beans` to the list merely for debugging convenience.

If not using Prometheus, the general metrics endpoint may be `/actuator/metrics`. Do not expose both `metrics` and `prometheus` if the scraper only needs one endpoint.

Exposure must be evaluated alongside the management port and base path. If the management listener runs separately, restrict network routes to that port; do not expose it through public ingress.

## 4. Creating a Separate Security Policy for Management Endpoints

When Spring Security is present, Actuator endpoints can be protected by a `SecurityFilterChain`. If the application declares its own chains, route management requests explicitly and ensure chain ordering is correct.

Illustrative configuration example:

~~~java
@Configuration
@EnableWebSecurity
public class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to("health"))
                        .permitAll()
                        .requestMatchers(
                                EndpointRequest.to("prometheus"))
                        .hasRole("MONITORING")
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .build();
    }
}
~~~

This is a skeleton example. You need Actuator/Security dependencies, an authentication provider, matchers, and endpoint IDs appropriate for your Spring Boot version. If health probes require unauthenticated access, permit only the needed health path/group. Never permit all of `/actuator/**`.

A dedicated chain prevents accidentally applying business API rules to management endpoints or vice versa. Test in practice to confirm requests hit the intended chain.

## 5. Creating a Dedicated Identity for the Scraper

The Prometheus scraper should have a dedicated identity solely for reading metrics. Never use administrator accounts, human operator accounts, or business application credentials.

A monitoring identity should:
- Only be allowed to GET the required metrics endpoint.
- Never call POST/DELETE or state-changing endpoints.
- Have no permission to read `env`/`configprops`/`heapdump`.
- Have environment-specific credentials or workload identity.
- Have a rotation cycle and revocation process.
- Be tracked in a secret manager and audit policy.

An in-memory user example is suitable only for local/test environments:

~~~java
@Bean
UserDetailsService monitoringUsers(PasswordEncoder encoder) {
    UserDetails scraper = User.withUsername("metrics-scraper")
            .password(encoder.encode("replace-with-secret"))
            .roles("MONITORING")
            .build();

    return new InMemoryUserDetailsManager(scraper);
}
~~~

Never commit illustrative passwords into source control. Production should pull credentials from secret management or integrate an appropriate identity provider. Across multiple replicas, identity and rotation must be rolled out consistently.

## 6. GET Permission Does Not Mean Admin Permission

Metrics scraping typically needs only HTTP GET. Policies should restrict both HTTP methods and endpoints instead of granting a broad administrative role.

Example target policy:

| Caller | GET `health` | GET `prometheus` | GET `env` | POST `shutdown` |
| --- | --- | --- | --- | --- |
| Kubelet probe | Allowed per network/policy | Denied | Denied | Denied |
| Metrics scraper | Per policy | Allowed | Denied | Denied |
| Operator | Per role | Per role | May be restricted | Denied by default |
| Public client | Only if design allows | Denied | Denied | Denied |

If a metrics endpoint only supports GET, there is no reason to grant write permission. If using the `MONITORING` role, do not reuse that role for other sensitive endpoints.

## 7. Basic Authentication, Tokens, and mTLS

There are several ways to authenticate scrapers:

### 7.1. HTTP Basic Authentication

Prometheus can send a username/password over HTTPS. Basic auth is simple, yet credentials must be protected as secrets and rotated. Never send Basic credentials over unencrypted HTTP.

### 7.2. Bearer Tokens

A reverse proxy, service mesh, or authentication layer can verify bearer tokens. Check issuer, audience, expiry, signature, and rotation. Do not write a custom JWT verification filter when the framework/security platform already provides a standard mechanism.

### 7.3. Mutual TLS

mTLS verifies client certificates at the TLS layer. You can restrict certificate issuer/SAN and map client identity into an authorization policy. mTLS protects the connection and authenticates the peer; you still must define which endpoints that certificate is permitted to read.

Do not enable overlapping mechanisms without clear ownership. For example, a proxy terminating mTLS while the application trusts identity headers from any source creates a vulnerability if the backend can be reached directly.

## 8. Prometheus Scrape Configuration and Secret Handling

Prometheus supports configuring authentication for scrape targets. Illustrative Basic auth example:

~~~yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    scheme: https
    static_configs:
      - targets:
          - order-service.internal:8081
    basic_auth:
      username: metrics-scraper
      password_file: /etc/prometheus/secrets/order-service-password
    tls_config:
      ca_file: /etc/prometheus/certs/internal-ca.pem
      server_name: order-service.internal
~~~

Examples must be adapted to your Prometheus version, deployment, and certificate topology. Use `password_file`/secret mounts or secret integrations—never write passwords directly into committed config files.

Protect all of these too:
- Prometheus configuration and generated configs.
- Secret files and file permissions.
- Prometheus backups/snapshots.
- Prometheus Admin API and UI.
- Remote write credentials and telemetry backends.
- Logs that might accidentally capture `Authorization` headers.

Scrape credentials are secrets capable of reading operational data. Rotation must update both scraper and target via a testable procedure.

## 9. Management Port and Network Isolation

Separating the management port helps restrict access paths, though it does not protect the port by itself. Example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Application traffic goes through 8080; management traffic through 8081. In Kubernetes, the public Service can target only port 8080; Prometheus uses Pod discovery or an internal-only Service pointing to 8081.

Network controls should:
- Allow only the Prometheus/monitoring namespace or subnet to reach the management port.
- Block public ingress to the management listener.
- Restrict egress/ingress by service identity when the platform supports it.
- Avoid binding loopback if the scraper sits in another network namespace.
- Verify NodePort/LoadBalancer/Ingress resources do not inadvertently expose the management port.

Network isolation complements application authentication. If a network policy is misconfigured, authorization remains the next line of defense.

## 10. TLS Termination and Reverse Proxies

If a reverse proxy terminates TLS, determine:
- Whether the proxy authenticates the scraper.
- Whether the proxy-to-application connection is encrypted or inside a trusted network.
- Whether the backend management port can be reached directly.
- Whether forwarded headers/identity headers are overwritten and protected by the proxy.
- Whether the proxy logs the `Authorization` header.

Never trust headers like `X-Remote-User` from arbitrary clients. Trust identity headers only when the backend accepts traffic exclusively from an authenticated proxy and the proxy always strips client-supplied headers before setting the verified value.

When possible, use mTLS between proxy and backend or workload identity. Never disable hostname verification to work around a certificate mismatch.

## 11. Metrics Can Also Contain Sensitive Data

Even when the endpoint is secured, metric contents must be designed safely.

Risks can come from:
- Labels containing user/customer/order IDs.
- URIs containing identifiers or query strings.
- Exception messages or SQL text turned into tags.
- Sensitive tenant/customer names.
- Metric names revealing internal features or dependencies.
- Label values indicating security state or activity of a small group.

Prefer low-cardinality labels: service, operation, method, outcome, status class, and route template. Never use metrics as a store for individual events or transactions.

Inspect both data before export and data already stored in Prometheus/remote backends. A leaked label can persist in retention, snapshots, and backups even after fixing code.

## 12. Testing Read Permissions With a Test Matrix

Test multiple identities and states, not just the valid scraper.

| Test | Expected Outcome |
| --- | --- |
| Scraper with valid credentials, GET `prometheus` | 200 |
| No credentials sent | 401 if endpoint requires authentication |
| Invalid credentials | 401 |
| Valid identity lacking role | 403 |
| Monitoring role calls `env` endpoint | 403 or endpoint unexposed/404 per policy |
| Monitoring role sends POST to metrics | 403/405 |
| Public network accesses management port | Connection blocked per network policy |
| Untrusted certificate | TLS handshake rejected |
| Valid certificate without authorization | Rejected at authorization |
| Scraper uses wrong path | 404 |

Exact status codes depend on the security chain, endpoint exposure, and proxy. The objective is ensuring callers can read only data within their authorized scope.

### 12.1. Testing With curl in a Test Environment

Example calling an endpoint with Basic auth:

~~~bash
curl --fail --user metrics-scraper \
  https://order-service.internal:8081/actuator/prometheus
~~~

`curl` will prompt for the password if omitted from the command line. Avoid writing secrets directly in shell history or process arguments. In production, use your operational environment's secret injection and appropriate tools.

Test negative cases with unauthenticated requests, bad credentials, and under-privileged roles. Never use an operator account to test scraper permissions.

## 13. Auditing and Rotation

Metrics read access must be operated as an access path with a full lifecycle:
- Who owns the scraper identity?
- Where are credentials stored?
- When are they rotated?
- How is a compromised target revoked?
- Are failed/successful accesses audit-logged?
- Are brute-force or abnormal scraping alerts in place?
- Do credentials appear in logs, traces, or crash dumps?

Frequent scraping can generate high volumes of access logs. Use an appropriate log policy: record identity, endpoint, status, and necessary source metadata; avoid recording `Authorization` headers or tokens.

Rotation should be deployable without prolonged monitoring downtime. Across multiple replicas, ensure every instance receives the new policy and old credentials are revoked after the scraper switches over.

## 14. Troubleshooting Metrics Read Permissions

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| 404 | Endpoint unexposed, missing registry, or wrong path | Exposure config, dependencies, base path |
| 401 | Missing/invalid credentials | Scraper secret, authentication provider |
| 403 | Authenticated identity lacks authority | Role mapping, matchers, chain order |
| 200 but missing expected metrics | Meter not registered or filter/export config | Registry, meter filters, instrumentation |
| Scrape timeout | Network path, TLS, overloaded management server | Connectivity, server metrics |
| TLS handshake failure | CA/SAN/protocol mismatch | Trust chain and server name |
| Scraper can access `env` | Overly broad matcher or shared role | Security chain, endpoint-specific authorization |
| Public caller can read metrics | Management port/ingress exposed broadly | Service, ingress, firewall, NetworkPolicy |
| Scrape fails after rotation | Target and scraper secrets out of sync | Rollout/rotation procedure |
| Backend shows credentials in logs | Proxy/app logs headers | Redact `Authorization` and check log pipeline |
| Metrics expose identifiers | High-cardinality or sensitive labels | Meter tags, URI conventions, redaction |
| Some replicas return 401/403 | Inconsistent config/secret rollout | Pod configuration and mounted secret versions |

### Investigation Workflow

1. Check target URL, scheme, port, and path.
2. Confirm the network route to the management listener.
3. Check TLS certificate, CA, and hostname.
4. Verify scraper identity and authentication method.
5. Check authorization rules, endpoint matchers, and filter-chain order.
6. Confirm endpoint exposure and registry/exporter.
7. Run the positive/negative access matrix.
8. Verify labels/responses do not leak out-of-scope data.
9. Cross-check logs without printing secrets.

## 15. Real-World Scenario: Only Prometheus May Read Metrics

**Context:** `order-service` runs in Kubernetes. Public APIs serve on port 8080; management port 8081 provides health and Prometheus metrics. Operations wants Prometheus to scrape metrics while blocking public clients from reading them.

### Step 1 — Separate the Management Listener

Configure `management.server.port` as 8081. The public Service targets only application port 8080.

### Step 2 — Restrict Exposure

Expose `health` and `prometheus`. Do not expose `env`, `configprops`, or other administrative endpoints.

### Step 3 — Create a Scraper Identity

Create a `metrics-scraper` identity with `MONITORING` authority. Store credentials in a secret store and mount them into Prometheus using platform-supported mechanisms.

### Step 4 — Authorization

The `SecurityFilterChain` permits only the `MONITORING` role to GET `prometheus`. Health probes are permitted per concrete policy. Remaining management endpoints are denied or unexposed.

### Step 5 — Network Isolation and TLS

A `NetworkPolicy` allows only the Prometheus namespace to reach port 8081. Scraping uses HTTPS with a trusted CA. Do not create a public ingress to the management listener.

### Step 6 — Testing

- Prometheus with credentials: scrape succeeds.
- Caller without credentials: rejected.
- Identity lacking role: rejected.
- Public network: cannot connect to management port.
- Metrics response contains no IDs or secrets in labels.
- Credential rotation does not disrupt scraping beyond the expected window.

**Desired outcome:** only a scraper with a valid identity and network path can read metrics; application APIs continue serving normal traffic.

## 16. Practice Exercises and Self-Check Questions

### Exercise A — Distinguishing Protection Layers

Diagram the flow from Prometheus to `/actuator/prometheus`. Mark network policy, TLS, authentication, authorization, endpoint exposure, and registry. Identify which layer produces 401/403/404/timeout errors.

### Exercise B — SecurityFilterChain

Create a dedicated chain for Actuator. Permit health probes per policy and require the `MONITORING` role for `prometheus`. Deny other endpoints. Test chain order and HTTP methods.

### Exercise C — Negative Access Tests

Send requests with no credentials, invalid credentials, insufficient role, and POST to metrics. Confirm no caller outside the policy can read the response.

### Exercise D — Prometheus Secrets

Configure scraping with a password file/secret mount and TLS CA. Verify secrets do not exist in source control, logs, or command history. Perform a rotation in a test environment.

### Exercise E — Network Isolation

In Kubernetes, have the public Service expose only the application port. Create internal management access for Prometheus. Verify NetworkPolicy and Pod discovery from the correct namespace.

### Exercise F — Metrics Privacy Review

Audit meter names and tag values. Remove user/order IDs, raw URIs, SQL text, and exception messages. Inspect both scrape responses and data stored in the backend.

### Self-Check Questions

1. How does endpoint exposure differ from authentication and authorization?
2. Why does a separate management port not automatically secure metrics?
3. What minimal permissions does a scraper need?
4. What do 401 and 403 typically indicate?
5. When is 404 a sign that an endpoint is not exposed?
6. Which layer must protect Basic authentication?
7. mTLS authenticates the peer, so why is authorization still needed?
8. How do you avoid trusting client-supplied identity headers?
9. Where should Prometheus store credentials?
10. Why should `env`/`configprops` not be exposed alongside metrics?
11. What data can metric labels reveal?
12. How do you verify read permissions using positive and negative tests?
13. Which components must be coordinated when rotating scraper credentials?
14. Why must Prometheus UI, API, and remote write also be secured?
15. How do you distinguish network, TLS, authentication, authorization, and registry errors?

**Completion criteria:** distinguish exposure/authentication/authorization/network; configure minimal GET metrics permissions; protect scraper credentials; use TLS/mTLS appropriately; restrict the management port; test 200/401/403/404; audit metric labels and auditing/rotation.

## 17. Takeaways

- Metrics are operational data that can disclose topology, routes, dependencies, and traffic patterns.
- Endpoint exposure only publishes an endpoint; it does not authenticate or authorize callers.
- Use a dedicated identity for the scraper and grant GET permission only on the required metrics endpoint.
- Protect scrapes with TLS; use mTLS or tokens when appropriate for your platform.
- A separate management port still needs network isolation and authorization; it is not an automatic security boundary.
- Never expose `env`, `configprops`, `heapdump`, or administrative endpoints to the `MONITORING` role.
- Prometheus credentials must reside in secret management, be rotated, and never appear in logs.
- Test positive and negative access cases: valid, missing credentials, bad credentials, missing role, out-of-policy methods/paths.
- Labels must be low-cardinality and contain no identifiers, PII, SQL text, or exception messages.
- Protect the metrics endpoint, Prometheus server, UI/API, remote write, and stored data alike.
- Use access auditing/monitoring to detect abnormal scrapes and drive rotation/revocation.

## References

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot Reference — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Prometheus — Configuration and Scrape Authentication](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OpenTelemetry — Data Security](https://opentelemetry.io/docs/security/)
