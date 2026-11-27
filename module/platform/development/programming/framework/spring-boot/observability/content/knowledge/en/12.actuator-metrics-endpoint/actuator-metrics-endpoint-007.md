# Metric Endpoints and Security

In the **Actuator metrics endpoint** chapter of the **SPRING_BOOT_OBSERVABILITY** module, opening an endpoint to view metrics is not just a matter of configuring a URL. Operators need to know **which endpoint serves diagnosis**, **which endpoint serves the scraping system**, **who is authorized to access it**, and **what information could leak** if misconfigured.

This module builds observability for Spring Boot using **Micrometer Observation, metrics, logs, and distributed tracing**, while teaching context propagation, tags/cardinality, exporters, and sampling to investigate errors, latency, and application behavior in production environments. The metrics endpoint is a window for reading data from the metrics branch of that system. It does not automatically emit logs or tracing spans, nor does it replace the application's security requirements.

**Core principle:** enable endpoints only when needed, restrict which users and networks can access them, secure the transport, and verify that securing endpoints **does not break the metrics collection pipeline**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `/actuator/metrics`, `/actuator/metrics/{name}`, and `/actuator/prometheus`.
2. Explain the difference between **an endpoint existing**, **an endpoint being exposed over HTTP**, and **an endpoint permitting a user to access it**.
3. Configure Spring Boot Actuator and the Micrometer Prometheus registry for a test environment.
4. Use Spring Security to allow only authorized users to read metrics; recognize behavior with and without a custom `SecurityFilterChain`.
5. Establish separate access principles for **operations staff** and the **Prometheus scraper service**.
6. Inspect HTTP 200, 401, 403, and 404 responses to diagnose configuration errors.
7. Assess risks of metadata exposure, cardinality, scrape overhead, and risks when bringing metrics endpoints to production.
8. Combine metric information with logs, tracing, and sampling during incident investigation.

## 2. Two Commonly Confused Endpoints

Spring Boot Actuator has many endpoints. When working with metrics, the most important ones fall into two categories:

| Endpoint | Purpose | Common Format | Consumer |
| --- | --- | --- | --- |
| `GET /actuator/metrics` | List meter names the application publishes via Actuator. | JSON | Developers/operators, inspection tools. |
| `GET /actuator/metrics/{metric.name}` | View measurements and available tag values of a meter; filterable by `tag`. | JSON | Anyone investigating a specific metric. |
| `GET /actuator/prometheus` | Export data in a format for Prometheus scraping. | Prometheus/OpenMetrics text, depending on content/format negotiation. | Prometheus or an authorized scraper. |

Example:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` is Actuator's **diagnostic** API, not the endpoint Prometheus normally uses to scrape. Prometheus uses the format at `/actuator/prometheus` when the Prometheus registry is enabled.

For an HTTP server timer, the name in Actuator may be `http.server.requests`, whereas the Prometheus exporter may emit series such as `http_server_requests_seconds_count` and `http_server_requests_seconds_sum`. This does not mean there are two independent metrics: the registry applies naming conventions, suffixes, and units appropriate for the backend.

### Data Returned by the Metrics Endpoint

Example of an **illustrative** response when calling `GET /actuator/metrics/http.server.requests`:

~~~json
{
  "name": "http.server.requests",
  "description": null,
  "baseUnit": "seconds",
  "measurements": [
    {"statistic": "COUNT", "value": 120.0},
    {"statistic": "TOTAL_TIME", "value": 14.2},
    {"statistic": "MAX", "value": 0.83}
  ],
  "availableTags": [
    {"tag": "method", "values": ["GET", "POST"]},
    {"tag": "status", "values": ["200", "500"]},
    {"tag": "uri", "values": ["/orders/{id}", "/checkout"]}
  ]
}
~~~

This is **not real output** from a project. Fields and values depend on meter type, registry, traffic, and Spring Boot version. Some meters have a different base unit or lack all the measurements in the example above.

Key meanings:

- `name` is the meter name in the Micrometer model.
- `measurements` holds aggregated measurements; e.g., `COUNT` and `TOTAL_TIME` of a timer.
- `availableTags` indicates filterable dimensions; this is also where unwanted tag cardinality can be spotted.
- A timer's `MAX` may be a time-windowed measurement; do not assume it is always the highest value since process startup.

**Never arbitrarily add or divide Actuator measurements and treat the result as system-wide P95.** Percentiles and histograms require proper distribution data from the exporter/backend.

## 3. Three Layers of Conditions: Enablement, Exposure, and Authorization

An endpoint can be **implemented in the application** yet unreachable over HTTP. Check three separate questions:

1. **Does the corresponding endpoint/registry exist?** For example, `/actuator/prometheus` requires the Prometheus registry and supporting auto-configuration.
2. **Is the endpoint exposed over HTTP?** `management.endpoints.web.exposure.include` determines the set of endpoints published over HTTP.
3. **Is the caller allowed to read it?** Spring Security, reverse proxies, service meshes, ingress, or network policies can block requests.

~~~mermaid
flowchart TD
    A["Client: GET /actuator/metrics"] --> B{"Endpoint configured and available?"}
    B -->|"No"| N["No matching endpoint"]
    B -->|"Yes"| C{"Exposed over HTTP?"}
    C -->|"No"| N
    C -->|"Yes"| D{"Passes network/ingress?"}
    D -->|"No"| T["Timeout / connection refused / proxy error"]
    D -->|"Yes"| E{"Authenticated and authorized?"}
    E -->|"No"| U["401 or 403 depending on case"]
    E -->|"Yes"| F["200 + data if endpoint works"]
~~~

**404** usually suggests the endpoint does not exist or is not exposed at that URL; **401** indicates unauthenticated per security policy; **403** usually indicates an authenticated identity that lacks permission. These are initial diagnostic heuristics, not an absolute contract: proxies and security filters may return different codes or intentionally hide endpoint existence.

An endpoint opened successfully locally is not guaranteed to be reachable after deployment behind ingress, a management port, or a service mesh.

## 4. Minimal Configuration for Spring Boot and Micrometer

Example **Spring Boot 3.x** application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator` provides the Actuator and metrics infrastructure. `micrometer-registry-prometheus` lets Spring Boot configure the Prometheus registry when conditions are met. Manage Micrometer versions via the Spring Boot BOM rather than arbitrarily mixing incompatible versions.

Example configuration **for controlled test environments only**:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Expected behavior when the application has metrics and runs on port 8080:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

Points to avoid confusing:

- Under typical Spring Boot defaults, **health** is the main endpoint exposed over the web; `metrics` or `prometheus` usually require declaring exposure.
- Adding exposure **does not decide** who is allowed to access it: that is the job of security and network infrastructure.
- If the Prometheus registry is absent or disabled, `/actuator/prometheus` may be unavailable even when listed in `include`.
- If `management.endpoints.web.base-path`, management port, or context path changes, URLs will no longer match the example.
- Enabling the metrics endpoint does not automatically populate data for a custom meter that has never been recorded.

Do not use `include: "*"` as a quick fix for a 404 in production. It can unintentionally expose many management endpoints unsuitable for external users.

## 5. How Does Spring Security Protect Actuator?

When **Spring Security** is on the classpath and you have not defined a custom `SecurityFilterChain`, Spring Boot typically provides default security rules for Actuator: the health endpoint is treated differently from other management endpoints. Exact behavior also depends on version, dependencies, and configuration.

**Especially important:** once an application defines a custom `SecurityFilterChain`, Spring Boot typically **backs off from Actuator security auto-configuration**. At that point, you must write access rules for Actuator yourself. You cannot assume "Actuator will always secure itself" if application security configuration is present.

Adding Spring Security:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

### An Illustrative Security Chain with Rules

Spring Security 6 / Spring Boot 3.x example where:

- `health` permits unauthenticated access, **if allowed by organizational policy**.
- `metrics` is restricted to users with role `OPS`.
- `prometheus` is restricted to the scraper identity with role `SCRAPER`.
- Remaining Actuator endpoints require `OPS`.
- Regular APIs still require authenticated users.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("metrics")).hasRole("OPS")
                .requestMatchers(EndpointRequest.to("prometheus")).hasRole("SCRAPER")
                .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**This example focuses only on authorization**; it does not define users, passwords, or how roles are granted. To run, the application must have an identity provider or authentication mechanism granting `ROLE_OPS` and `ROLE_SCRAPER` per Spring Security conventions. `httpBasic` is chosen for easy testing on an internal network; in production, you can use OAuth2/OIDC, mTLS, or an appropriate service account authentication mechanism. **Never send Basic credentials over unencrypted HTTP.**

If the application already uses an OAuth2 resource server, multiple `SecurityFilterChain` beans, CSRF/HTTP sessions, or complex API authorization, integrate Actuator rules into the existing architecture rather than copying a global chain and inadvertently altering API behavior. `EndpointRequest` matches endpoints via Actuator's mechanism instead of relying solely on fixed URL strings.

### Separating the Metrics-Reader Role and Scraper Role

Having two separate roles follows the principle of **least privilege**:

| Access Group | Need | Recommended Permissions |
| --- | --- | --- |
| Developer/Ops investigating an incident | List, filter, and inspect individual JSON meters. | Only needed endpoints such as `metrics`. |
| Prometheus service account | Read data on a periodic schedule. | Only `prometheus` over permitted networks. |
| Health checker | Simple status check. | Only public-appropriate health info. |
| Regular API user | Use business functionality. | No access needed to metrics endpoints. |

You do not have to use the exact role names from the example; what matters is mapping them to real permissions from your identity system and testing cross-access cases.

## 6. Protecting with Network Boundaries and a Management Port

**Application-layer authorization is necessary but not sufficient.** Metrics endpoints can be reached along multiple paths: directly to a pod, through an internal service, through public ingress, or through a sidecar/proxy. Clear network boundaries must be established.

A common architecture:

~~~mermaid
flowchart LR
    Client["Internet Users"] --> Public["Public ingress"]
    Public --> API["Spring Boot API port"]
    Collector["Prometheus on internal network"] --> Private["Private service / management ingress"]
    Private --> Mgmt["Actuator management port"]
    OPS["Ops via VPN / bastion"] --> Private
    Mgmt --> Registry["MeterRegistry / Actuator"]
    API --> Registry
~~~

Actuator can run on a separate management port:

~~~yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

With this configuration and appropriate defaults, inspection URLs may be `http://localhost:9091/actuator/metrics` instead of application port 8080.

**A separate port does not mean a secure port.** If port 9091 is still exposed via a public load balancer or an unrestricted pod network, risk remains. Restrict ingress/sources, access rights, and TLS. Binding to `127.0.0.1` may suit a local/sidecar scraper, yet can block a remote Prometheus from connecting. Design alongside the actual deployment topology.

Measures commonly combined:

- Place metrics endpoints on an **internal management network**, avoiding unnecessary routing through public ingress.
- Use **TLS** for connections reading metrics over the network; consider mTLS for service-to-service traffic.
- Apply network policies, firewalls, security groups, service mesh authorization, or proxy ACLs.
- Grant minimal identity/role to the scraper, rotate credentials, and store secrets in a secret manager.
- Limit exposed endpoints; do not turn a scraping issue into an excuse to expose all management endpoints.
- Monitor HTTP status, scrape duration, authentication failure counts, and request volume to management endpoints.

## 7. Does the Prometheus Scrape Endpoint Require Authentication?

**Yes, according to the system's access policy.** A common design exposes `/actuator/prometheus` only to the Prometheus scraper over a private network; if authentication is enabled, the scraper must have valid credentials. Allowing the scraper access does not mean Internet users may read the endpoint.

An example Prometheus configuration for a management endpoint behind a secured TLS proxy:

~~~yaml
scrape_configs:
  - job_name: "order-api"
    scheme: https
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - order-api-management.internal:9443
    basic_auth:
      username: scraper
      password_file: /etc/prometheus/secrets/order-api-password
~~~

This is an **illustrative topology**: hostname, port, TLS termination, and secret file must be provisioned beforehand. Prometheus will not create them automatically. Passwords must not be hard-coded in source code or exposed in public config; secret files need proper file permissions. In environments supporting OAuth2, bearer tokens, mTLS, or proxy-based authentication, choose the mechanism meeting organizational requirements.

A common mistake is securing endpoints with Spring Security while forgetting to update scrape configuration. Result: manual checks with valid credentials return 200, while the Prometheus target returns **401** or **403**. Directly inspect **target status** and the HTTP response from the exact address Prometheus hits.

### The Scraper Does Not Use `/actuator/metrics` as Its Default Endpoint

`/actuator/metrics` returns JSON for diagnosis. Prometheus requires the format exported by the Prometheus registry at `/actuator/prometheus`. Pointing `metrics_path` to the wrong endpoint can cause parse errors, wrong content types, or missing expected series even when HTTP status is 200.

## 8. Querying a Metric and Filtering by Tag

Once properly authorized, list names:

~~~bash
curl -s -u ops http://localhost:9091/actuator/metrics
~~~

`curl -u ops` normally prompts interactively for a password if omitted; avoid placing passwords in shell history. Test only over localhost or HTTPS in secured environments.

Example querying a specific meter:

~~~bash
curl -s -u ops http://localhost:9091/actuator/metrics/http.server.requests
~~~

You can filter by one or more tag pairs:

~~~bash
curl -s -u ops --get \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=status:200" \
  http://localhost:9091/actuator/metrics/http.server.requests
~~~

The `tag=key:value` parameter limits aggregation in the Actuator response to the supplied tags. It is **not PromQL**, not an arbitrary query language, and does not look up all request traces.

If a service has routes like `/orders/{id}`, normalize routes to templates in HTTP metrics instead of using URLs containing actual order IDs. You can filter `uri` using values from `availableTags`. This controls cardinality and prevents leaking information in metadata.

**Never let request IDs, user IDs, emails, access tokens, or raw paths containing personal data become metric tags.** Protecting the endpoint with authentication does not fix a backend overwhelmed by huge series volumes from high-cardinality tags.

## 9. Why Are Metrics Endpoints Also Assets That Must Be Protected?

Metrics usually have no request bodies, yet they can reveal:

- Service names, internal routes, dependencies, pools, and runtime structure.
- Transaction frequency, error ratios, saturation states, or peak activity windows.
- Partition, environment, or instance labels, or internally meaningful component names.
- If instrumentation is poorly designed: request IDs, customer names, detailed URLs, and sensitive values inside tags.

Therefore, endpoint security is not just to hide dashboards from outsiders, but also to prevent **metadata leakage**, **unauthorized architecture reconnaissance**, and **excessive querying**. Scrape payloads can be large when an application has many meters/series; an endpoint polled continuously by untrusted sources can load the process and network.

Key controls include authentication and authorization, TLS, network restrictions, request rate monitoring, cardinality limits at the source, and backend retention policies. Controls like rate limiting should be implemented at the proxy/ingress or appropriate layer so legitimate scraping is not disrupted.

Do not use information from metrics endpoints as authorization or user authentication evidence. This is telemetry, not a trusted identity source.

## 10. Endpoint Exposure Does Not Replace Metric-Layer Filters

A common misconception: "Hiding `/actuator/metrics` stops the application from recording metrics." In reality, these are two separate concerns:

- **Exposure** decides whether the endpoint can be reached over HTTP.
- **`MeterRegistry`** can still record metrics into its registry implementation even when the endpoint is not exposed.
- **`MeterFilter`** can affect meter registration, modify names/tags, or deny a group of meters.
- **`ObservationPredicate`** can drop an observation at the Micrometer Observation layer; that is not an HTTP authorization policy.
- **Tracing sampling** decides which fraction of traces are recorded/kept, not access control for metrics endpoints.

For example, if an application records `checkout.completed` into `MeterRegistry` while `/actuator/metrics` is unexposed, a scraper using another exporter may still receive metrics depending on the system. Conversely, if the metrics endpoint is publicly exposed while a `MeterFilter` drops a meter, making the endpoint public does not bring back the dropped meter.

**Endpoint security is an access-control problem; cardinality and sampling are telemetry quality/cost problems.** Both must be addressed without conflating them.

## 11. Connecting Metrics with Logs and Distributed Tracing During Investigation

Suppose `order-api` experiences an incident: from 10:20 to 10:30, P95 of `GET /orders/{id}` rises from 180 ms to 1.2 seconds.

A sound workflow:

1. **Metrics:** inspect count, error rate, and duration by route, method, status, and instance in Prometheus. If a single process appears affected, check JVM, CPU, and connection pool metrics for that instance.
2. **Actuator diagnostic endpoint:** if you need to verify the metric source, read `/actuator/metrics/http.server.requests` using OPS permissions; compare `availableTags` and measurements.
3. **Logs:** look for timeouts, retries, and exceptions in the same time range; look up `traceId` if logging/MDC integration is configured.
4. **Distributed tracing:** open several slow and normal traces to see which dependency caused delay and which span sits on the critical path.
5. **Propagated context:** if a trace breaks at an HTTP client or messaging boundary, check `traceparent`, instrumentation, and async context rather than assuming the metrics endpoint is wrong.
6. **Sampling/exporters:** if metrics show many failing requests while no matching trace is found, consider trace sampling out or collector/exporter errors; metrics and tracing have separate pipelines.
7. **Verify remediation:** after fixing, re-check error rate and latency across a sufficiently large sample of requests, then cross-check new logs/traces if needed.

An Actuator metrics endpoint returning 200 only proves **the endpoint's metric read path worked at that moment**. It does not prove Prometheus scraped successfully, the trace exporter is working, or dashboard data is up to date.

## 12. Quick Diagnostic Table by HTTP Status

| Symptom | Common Hypothesis | Check Action |
| --- | --- | --- |
| **404** at `/actuator/metrics` | Endpoint not exposed, disabled, or different management base path/port. | Check exposure and actual management URL. |
| **404** at `/actuator/prometheus` | Missing Prometheus registry or endpoint not exposed/enabled. | Check `micrometer-registry-prometheus` dependency and endpoint config. |
| **401 Unauthorized** | Unauthenticated or scraper credentials wrong. | Check security chain, authentication provider, and scraper identity. |
| **403 Forbidden** | Caller lacks permission; sometimes related to other security/proxy policies. | Check roles/authorities and access-control rules. |
| **200** but JSON has only a few names | No traffic yet, meters not recorded, missing binders, or filtered out by meter filter. | Trigger business paths and inspect registry/metric names. |
| **200** at `/metrics`, Prometheus target still down | Scraper uses different network path, URL, credentials, or TLS. | Test from scraper's network and check target status. |
| **200** at `/prometheus` but expected metric missing | Meter not created, name converted, wrong tags, or filtered out. | Find meter name in Actuator and compare raw exporter response. |
| Timeout/connection refused | Network policy, firewall, management port, ingress, or process not ready. | Check reachability along the actual scraper path. |
| After deploy, endpoint suddenly publicly open | New security chain omitted Actuator or public ingress routed to management port by mistake. | Review authorization, ingress/network policies, and test from untrusted network. |

When handling 404s, avoid immediately switching to `include: "*"`. That is a convenient fix that can widen the attack surface. Expose **only** the required endpoints and maintain least-privilege access policies.

## 13. Pre-Deployment Security Testing

Checks to include in pipelines or deployment verification:

### 13.1 Verify Public Paths Cannot Read Metrics

From a location resembling an Internet user's network path, send an unauthenticated request to management URLs if that route might be reachable:

~~~bash
curl -i https://public.example.invalid/actuator/metrics
curl -i https://public.example.invalid/actuator/prometheus
~~~

The domain `example.invalid` is just a placeholder, not a real host. Desired outcomes depend on architecture: no route, timeout at the network boundary, 401, or 403. **Never treat 200 as a pass for this negative test.**

### 13.2 Verify Ops and Scraper Have Appropriate Permissions

In a protected environment:

~~~bash
curl -i -u ops https://management.example.invalid/actuator/metrics
curl -i -u scraper https://management.example.invalid/actuator/prometheus
~~~

The example omits passwords from the command line; `curl` prompts for a password when `-u <username>` is used interactively. If the system uses mTLS, bearer tokens, or an identity proxy, adapt the test to the real authentication mechanism.

Also test **cross-access denial**: the scraper should not be able to read arbitrary Actuator endpoints, and regular API accounts should not be able to read metrics.

### 13.3 Check for Leaked Content

Inspect tag lists and sample metrics:

- Are request IDs, user IDs, emails, tokens, or raw URLs used as tags?
- Are routes normalized to templates?
- Are unnecessary dependency, server, pool, or business names exposed?
- Which details belong only in access-controlled logs/traces?

If high-cardinality or sensitive tags exist, fix instrumentation or apply appropriate filters. **Authorization does not replace safe metadata design.**

### 13.4 Verify Scrape Health

After applying access control, verify the Prometheus target stays **UP** and scrape duration is normal. Check HTTP 200, content type, and desired metric data from the scraper's actual network. An operator opening the endpoint manually on a laptop is not enough to confirm the scraper has connectivity and read permissions.

## 14. Operational Checklist

- [ ] Expose only `health`, `metrics`, `prometheus`, or genuinely needed endpoints.
- [ ] Clearly distinguish the `/actuator/metrics` JSON API from the `/actuator/prometheus` exporter.
- [ ] Include the Prometheus registry when Prometheus-format scraping is actually needed.
- [ ] Enforce authentication/authorization both with default Spring Security and when configuring a custom `SecurityFilterChain`.
- [ ] Grant Ops and the scraper service account only the permissions they require.
- [ ] Keep management endpoints inside an appropriate network boundary; use TLS/mTLS if policy requires.
- [ ] Ensure management port, base path, and ingress are not accidentally exposed to the Internet.
- [ ] Test from an unauthorized location and confirm metrics do not unexpectedly return 200.
- [ ] Confirm the scraper still connects over the proper network, auth, and TLS after applying security.
- [ ] Ensure metric tags contain no request IDs, user IDs, emails, tokens, or cardinality-exploding values.
- [ ] Distinguish endpoint exposure issues from `MeterRegistry`, `MeterFilter`, tracing sampling, and exporter issues.
- [ ] Maintain a runbook correlating metrics with logs/traces when investigating errors and latency.

## 15. Self-Check Exercises

### Exercise 1: Which Endpoint Is for Prometheus?

An application has two URLs:

~~~text
/actuator/metrics
/actuator/prometheus
~~~

**Question:** Which URL should Prometheus scrape and why?

**Answer:** Normally `/actuator/prometheus` when the Prometheus registry is configured, because it exports metrics in Prometheus format. `/actuator/metrics` is a JSON API for listing and diagnosing meters, not an equivalent scrape endpoint.

### Exercise 2: `SecurityFilterChain` Present, Metrics Still Leaked

An application has Spring Security and a custom `SecurityFilterChain` for its API. After deploy, `/actuator/metrics` returns 200 to unauthenticated clients.

**Question:** What should be checked first?

**Answer:** Check the matchers and scope of security filter chains: a custom chain can cause Spring Boot to back off from default Actuator security, or the management route may bypass the intended chain. Also inspect ingress and management context—never simply add `spring-boot-starter-security` and assume everything is secured.

### Exercise 3: Does 404 Prove There Are No Metrics?

`/actuator/metrics` returns 404, yet the application still records a `Counter` into `MeterRegistry`.

**Answer:** No. HTTP exposure/enablement and recording metrics into a registry are two separate layers. Check URL, port, endpoint exposure, and registry; data may still be exported to another backend.

### Exercise 4: Scraper Role

A Prometheus service account only needs to read `/actuator/prometheus`, yet it is granted a role covering all endpoints including `env`, `configprops`, and `heapdump`.

**Question:** Is this an appropriate design?

**Answer:** No. Those permissions are far too broad for a scraping task. Grant least-privilege access strictly to the exporter endpoint and restrict network/TLS; avoid exposing sensitive management endpoints.

### Exercise 5: Target Goes DOWN After Enabling Authentication

Ops calls `/actuator/prometheus` with a personal account and gets 200; the Prometheus target transitions from UP to DOWN with 401.

**Answer:** Check the scraper's credentials/identity, `basic_auth` or other auth configuration, the `SCRAPER` role, secret rotation, and target URL. Do not remove security just to make the target UP; fix access permissions properly and re-verify.

**Key takeaway:** `/actuator/metrics` is the **diagnostic metrics API**, and `/actuator/prometheus` is the **export path for scrapers**. Both must be governed by **minimal exposure, least-privilege authorization, secure management networks, and metadata protection**. Only when metric read paths are reliable and not over-exposed can they effectively support correlating metrics, logs, and distributed tracing to uncover real causes of errors and latency.
