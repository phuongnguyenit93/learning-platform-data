# Metrics by Endpoint, Grant Type, Client, and Outcome

An Authorization Server handles requests that directly affect access control: login, requesting authorization codes, issuing tokens, refreshing tokens, introspection, and token revocation. When monitoring only CPU, memory, or overall HTTP request counts, operations teams struggle to tell which grant type is failing, which client has a high failure rate, or which endpoint is experiencing unusual latency spikes.

For the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, metrics must reflect client management, consent, token issuance, PKCE, refresh tokens, endpoint protection, and key signing. This lesson belongs to the **Observability and Auditing** chapter and guides you through designing metrics across four dimensions: endpoint, grant type, client, and outcome. These metrics help detect protocol incidents and support operations without exposing tokens or user-identifying data.

## 1. Defining Operational Questions Before Creating Metrics

A useful metrics suite must answer concrete questions:

- Which endpoint receives the most requests, and which endpoint has high p95/p99 latency?
- Which grant type has a rising error rate, such as **authorization_code**, **client_credentials**, or **refresh_token**?
- Which client is sending many failing requests or showing signs of excessive retries?
- What proportion of requests succeed, fail due to client errors, grant errors, or server errors?
- How does traffic change after deploying a new version, modifying client configuration, or rotating signing keys?

These four dimensions should be standardized into tags with bounded value sets:

| Dimension | Example Values | Rule |
|---|---|---|
| **endpoint** | **authorize**, **token**, **introspect**, **revoke**, **userinfo**, **jwks** | Map from configured endpoints; never use arbitrary URLs |
| **grant_type** | **authorization_code**, **client_credentials**, **refresh_token**, **other**, **none** | Keep only known grant types |
| **client** | **browser_public**, **orders_service**, **admin_console**, **unresolved** | Map registered client IDs to stable operational labels |
| **outcome** | **success**, **redirect**, **client_error**, **server_error**, **exception**, **other** | Group HTTP statuses into meaningful categories |

For example, one metric series can represent token endpoint requests using Client Credentials from a service client that completed successfully. Another series can represent rejected refresh token grants. By filtering across the four tags, dashboards can compare flows without reading tokens or sensitive payloads.

**redirect** is a normal outcome at the authorization endpoint because the server routinely redirects the browser to a login, consent, or callback page. For the token endpoint, success is typically HTTP 2xx; protocol errors are typically 4xx. Do not lump every non-2xx status into a single error category without considering endpoint characteristics.

## 2. Using Spring Boot Actuator and Micrometer

Spring Boot Actuator provides management endpoints, while Micrometer provides the API to record Counters, Timers, and Gauges. For an Authorization Server running on Spring Boot 3, you can add Actuator and the Prometheus registry:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

If the project uses Maven, add the equivalent dependencies with the same Spring Boot BOM version. Do not pin a Micrometer version different from the one managed by Spring Boot without a clear compatibility reason.

Configure management endpoints in the operational profile:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        oauth.server.endpoint.requests: true
~~~

**/actuator/metrics** helps inspect meters during development; **/actuator/prometheus** exports metrics in Prometheus format. Allow only internal monitoring systems to access management endpoints. Do not expose metrics endpoints publicly alongside user-facing APIs without appropriate authentication and network policies.

For request duration, use a Timer instead of only incrementing a Counter. A Timer automatically records both the count and total time, and can export histograms for percentile calculations. Tags must be present when the meter is created; do not add dynamic tags afterward.

## 3. Normalizing Endpoint, Grant Type, Client, and Outcome

Before recording metrics, convert request data into bounded labels:

- Endpoint is taken from the list of configured OAuth/OIDC routes. For example, **/oauth2/token** becomes **token**, and **/oauth2/authorize** becomes **authorize**.
- Grant type is taken from **grant_type** in a token request. For the authorization endpoint, **response_type=code** can be mapped to **authorization_code**; endpoints not tied to a grant type use **none**.
- Client is mapped from RegisteredClient to a label defined in operational configuration. Do not use every raw **client_id** value sent by requests directly as a tag.
- Outcome is determined from the HTTP status after the filter chain finishes: 2xx is **success**, 3xx is **redirect**, 4xx is **client_error**, 5xx is **server_error**; an exception not handled into a response is **exception**.

Example client mapping table:

~~~java
Map<String, String> clientMetricLabels = Map.of(
        "browser-public-client", "browser_public",
        "orders-service", "orders_service",
        "admin-console", "admin_console"
);
~~~

Clients that are unrecognized or not on the allowlist are assigned **unresolved**. For confidential clients using HTTP Basic, **client_id** typically resides in the Authorization header rather than a form parameter. Therefore, once authentication succeeds, retrieve RegisteredClient from the authentication object produced by Spring Authorization Server. For requests that fail before authentication completes, the client label can be **unresolved**; do not attempt to log raw credentials to make dashboards more granular.

## 4. Measuring OAuth/OIDC Requests with a Filter

Spring Authorization Server's token and authorization endpoints are handled by the security filter chain, not standard Spring MVC controllers. One integration approach is adding a **OncePerRequestFilter** to the Authorization Server SecurityFilterChain before the client authentication filter so failed authentication requests are also measured. The filter records metrics only for allowlisted routes.

The example below measures processing duration while attaching endpoint, grant type, client, and outcome tags:

~~~java
public final class OAuthEndpointMetricsFilter extends OncePerRequestFilter {

    private static final Map<String, String> ENDPOINTS = Map.of(
            "/oauth2/authorize", "authorize",
            "/oauth2/token", "token",
            "/oauth2/introspect", "introspect",
            "/oauth2/revoke", "revoke",
            "/oauth2/jwks", "jwks",
            "/userinfo", "userinfo"
    );

    private static final Set<String> GRANT_TYPES = Set.of(
            "authorization_code",
            "client_credentials",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:token-exchange"
    );

    private final MeterRegistry meterRegistry;
    private final Map<String, String> clientMetricLabels;

    public OAuthEndpointMetricsFilter(
            MeterRegistry meterRegistry,
            Map<String, String> clientMetricLabels) {
        this.meterRegistry = meterRegistry;
        this.clientMetricLabels = Map.copyOf(clientMetricLabels);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !ENDPOINTS.containsKey(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String endpoint = ENDPOINTS.get(request.getServletPath());
        String grantType = resolveGrantType(request, endpoint);
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "exception";

        try {
            filterChain.doFilter(request, response);
            outcome = resolveOutcome(response.getStatus());
        } catch (IOException | ServletException | RuntimeException ex) {
            outcome = "exception";
            throw ex;
        } finally {
            String client = resolveClientLabel(request);
            sample.stop(Timer.builder("oauth.server.endpoint.requests")
                    .description("OAuth and OIDC endpoint request duration")
                    .tag("endpoint", endpoint)
                    .tag("grant_type", grantType)
                    .tag("client", client)
                    .tag("outcome", outcome)
                    .register(meterRegistry));
        }
    }

    private String resolveGrantType(
            HttpServletRequest request, String endpoint) {
        if ("authorize".equals(endpoint)) {
            return "code".equals(request.getParameter("response_type"))
                    ? "authorization_code" : "other";
        }
        if (!"token".equals(endpoint)) {
            return "none";
        }
        String requestedGrant = request.getParameter("grant_type");
        return requestedGrant != null && GRANT_TYPES.contains(requestedGrant)
                ? requestedGrant : "other";
    }

    private String resolveClientLabel(HttpServletRequest request) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication instanceof OAuth2ClientAuthenticationToken clientAuth
                && clientAuth.isAuthenticated()
                && clientAuth.getRegisteredClient() != null) {
            String clientId = clientAuth.getRegisteredClient().getClientId();
            return clientMetricLabels.getOrDefault(clientId, "unresolved");
        }

        String requestedClientId = request.getParameter("client_id");
        if (requestedClientId == null || requestedClientId.isBlank()) {
            return "unresolved";
        }
        return clientMetricLabels.getOrDefault(requestedClientId, "unresolved");
    }

    private String resolveOutcome(int status) {
        if (status >= 200 && status < 300) return "success";
        if (status >= 300 && status < 400) return "redirect";
        if (status >= 400 && status < 500) return "client_error";
        if (status >= 500) return "server_error";
        return "other";
    }
}
~~~

Key imports include **java.util.Map**, **java.util.Set**, **io.micrometer.core.instrument.MeterRegistry**, **Timer**, **jakarta.servlet.FilterChain**, **ServletException**, **HttpServletRequest**, **HttpServletResponse**, **org.springframework.web.filter.OncePerRequestFilter**, **Authentication**, **SecurityContextHolder**, and **OAuth2ClientAuthenticationToken** from the **org.springframework.security.oauth2.server.authorization.authentication** package. The filter is registered relative to **OAuth2ClientAuthenticationFilter** from the **org.springframework.security.oauth2.server.authorization.web.authentication** package. The cardinality-limiting configuration uses **io.micrometer.core.instrument.config.MeterFilter** and **org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer**.

The **ENDPOINTS** list is an example for default endpoint URIs. If the application changes URIs in **AuthorizationServerSettings**, update the mapping table to match the actual configuration. Never use raw **request.getRequestURI()** as a tag because unrecognized URLs can produce an unbounded number of values.

In the example, **OAuth2ClientAuthenticationToken** lets you retrieve RegisteredClient after client authentication succeeds. For requests that fail before authentication, the filter can only inspect the untrusted client_id parameter if present and map it through the allowlist; otherwise it uses **unresolved**. This avoids attributing a verified identity to a request that merely declared a client ID.

Place the filter in the Authorization Server SecurityFilterChain, before **OAuth2ClientAuthenticationFilter**:

~~~java
http.addFilterBefore(
        oauthEndpointMetricsFilter,
        OAuth2ClientAuthenticationFilter.class
);
~~~

Add the filter only to the chain handling Authorization Server endpoints. If the filter is declared as a Filter bean in Spring Boot, disable automatic servlet container registration via **org.springframework.boot.web.servlet.FilterRegistrationBean#setEnabled(false)** and add it manually to the security chain. Otherwise, the filter may run twice or run outside the intended security scope.

The sample filter measures all requests to allowlisted routes. When adding new or custom endpoints, add static mappings and corresponding tests. For OIDC logout or other specialized endpoints, clearly define valid routes and outcomes before adding them to the same meter.

## 5. Limiting Cardinality and Protecting Sensitive Data

Micrometer creates a meter for each tag combination. With 8 endpoints, 5 grant types, 100 clients, and 5 outcomes, a single meter can generate up to 20,000 combinations before adding any other tags. When arbitrary client IDs, user IDs, or URLs are placed into tags, meter counts can grow uncontrollably, increasing RAM usage, Prometheus costs, and query latency.

Apply the following rules:

- Only use endpoints, grant types, and outcomes from an allowlisted set of values.
- Only use normalized client labels; set a limit on how many clients appear individually on detailed dashboards.
- Never use subject, username, email, tenant ID, session ID, or IP address as tags.
- Never use access tokens, refresh tokens, authorization codes, client secrets, state, code verifiers, or request bodies as tags or log fields.
- Never use redirect URIs, query strings, exception messages, or free-form error strings as tags.
- Do not add scopes or scope combinations as tags unless there is a clear measurement need; use redacted logs/audits or separate reporting when necessary.

You can set a client tag limit at the MeterRegistry level:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> oauthMetricCardinalityLimit() {
    return registry -> registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                    "oauth.server.endpoint.requests",
                    "client",
                    30,
                    MeterFilter.deny()
            )
    );
}
~~~

**MeterFilter** is an additional safeguard. It does not replace normalizing tags before recording. If the number of valid clients exceeds the limit, select a group of critical clients to label individually and group the rest into **other_client**, while providing separate reporting for per-client analysis if needed.

Metrics are aggregated numbers. Audit logs are records of individual events requiring traceability. If you need to know who approved consent or which client was revoked, record audit events with access control, retention, and masking. Do not try to turn metrics into a detailed event store by placing personal identifiers into tags.

## 6. Reading Metrics in Prometheus

A Micrometer Timer can be exported by the Prometheus registry as series such as:

- **oauth_server_endpoint_requests_seconds_count**: total number of measurements.
- **oauth_server_endpoint_requests_seconds_sum**: total processing time.
- **oauth_server_endpoint_requests_seconds_bucket**: duration histogram by bucket.

Metric names convert dots to underscores, and time units are expressed in seconds. You can use the following PromQL queries.

**Request rate by endpoint, grant type, client, and outcome:**

~~~promql
sum by (endpoint, grant_type, client, outcome) (
  rate(oauth_server_endpoint_requests_seconds_count[5m])
)
~~~

**p95 latency by endpoint and grant type:**

~~~promql
histogram_quantile(
  0.95,
  sum by (le, endpoint, grant_type) (
    rate(oauth_server_endpoint_requests_seconds_bucket[5m])
  )
)
~~~

**Error request ratio across OAuth/OIDC endpoints:**

~~~promql
sum(
  rate(oauth_server_endpoint_requests_seconds_count{
    outcome=~"client_error|server_error|exception"
  }[5m])
)
/
clamp_min(
  sum(rate(oauth_server_endpoint_requests_seconds_count[5m])),
  0.000001
)
~~~

**Error ratio by client:**

~~~promql
sum by (client) (
  rate(oauth_server_endpoint_requests_seconds_count{
    outcome=~"client_error|server_error|exception"
  }[5m])
)
/
clamp_min(
  sum by (client) (
    rate(oauth_server_endpoint_requests_seconds_count[5m])
  ),
  0.000001
)
~~~

For error ratio queries, select the right endpoint and outcome groups for the dashboard. A 302 redirect at the authorization endpoint is usually a normal part of the login flow and should not be counted as an error. Likewise, some 4xx responses may be malformed requests from clients; they are still protocol errors worth observing, though not necessarily server availability failures.

## 7. Designing Dashboards Around Operational Needs

A dashboard can be organized into four panels:

| Section | Chart | Question to Answer |
|---|---|---|
| Endpoint overview | Request rate and p95/p99 by endpoint | Where are traffic and latency increasing? |
| Grant type | Request rate and error rate by grant | Are Client Credentials, Authorization Code, or Refresh Token having issues? |
| Client | Top clients by request rate and errors | Which client is retrying heavily or sending invalid requests? |
| Outcome | Success, redirect, client_error, server_error, exception | Are errors coming from requests, authentication, grant processing, or the server? |

For the token endpoint, track Client Credentials and Refresh Token separately because they have different authentication models and lifecycles. A spike in **invalid_client** may relate to a rotated secret that a client has not updated yet; a spike in **invalid_grant** may relate to expired authorization codes, wrong PKCE verifiers, or replayed refresh tokens. Aggregated metrics surface trends, while audit events and masked logs help investigate individual cases.

Maintain a dashboard comparing before and after each deployment. If request rate remains steady while p95 spikes suddenly, check dependencies such as the database, key store, DNS, introspection, or JWKS. If only one client exhibits rising errors, inspect that client's configuration, secret rotation, and retry policy before attributing the fault to the entire Authorization Server.

## 8. Setting Up Context-Aware Alerts

Do not alert solely on absolute increases in 4xx counts, because some clients may send invalid requests during normal operation. Combine error ratio, minimum traffic volume, and sustained duration:

- **Server error:** alert when the server_error or exception ratio exceeds a threshold for several minutes with enough requests to be statistically meaningful.
- **Token endpoint latency:** alert when p95 exceeds the agreed SLO over a continuous window.
- **Client failure spike:** alert per allowlisted client when client_error rises abnormally above baseline.
- **Traffic drop:** alert when authorization/token traffic drops abruptly if the system has expected baseline load.
- **Unresolved client spike:** alert when requests with an unresolved client surge, which may indicate misconfigured clients or scanning traffic.

Example simple PromQL expression for server error ratio:

~~~promql
sum(rate(oauth_server_endpoint_requests_seconds_count{
  outcome=~"server_error|exception"
}[5m]))
/
clamp_min(
  sum(rate(oauth_server_endpoint_requests_seconds_count[5m])),
  0.000001
)
> 0.02
~~~

The 2% threshold is purely illustrative. Choose real thresholds based on SLOs, baseline traffic, endpoint type, and impact severity. Do not apply the same threshold to every endpoint: the authorization endpoint normally emits redirects, whereas the token endpoint needs protocol errors and server errors analyzed separately.

## 9. Testing Metrics

Metrics must be tested as part of observability configuration. Use **SimpleMeterRegistry** in unit tests or the registry configured in the Spring test context. A successful token endpoint test can verify that the Timer is recorded with the expected tags:

~~~java
Timer timer = meterRegistry.find("oauth.server.endpoint.requests")
        .tags(
                "endpoint", "token",
                "grant_type", "client_credentials",
                "client", "orders_service",
                "outcome", "success"
        )
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isGreaterThanOrEqualTo(0);
~~~

Add tests covering:

- Token requests using an unknown grant type: the tag must be **other**, never generating arbitrary tags.
- Requests to the authorization endpoint with **response_type=code**: the grant tag is **authorization_code**.
- Authorization requests redirecting to login/consent: outcome is **redirect**.
- Valid clients: the client tag is the configured label, not the raw client ID.
- Unauthenticated clients: the client tag is **unresolved** when a trustworthy identity cannot be determined.
- Token endpoint returning 4xx or 5xx: outcome reflects the corresponding status class.
- Requests to non-allowlisted URLs: the filter does not record OAuth endpoint meters.
- The filter executes only once inside the Authorization Server SecurityFilterChain and is not registered a second time by the servlet container.

Check the **/actuator/prometheus** endpoint to verify meters are scrapeable. Also verify that the metrics response contains no access tokens, refresh tokens, authorization codes, client secrets, usernames, or email addresses.

## 10. Combining Metrics, Logs, and Audits

These three data sources answer different questions:

| Source | Purpose | Appropriate Content |
|---|---|---|
| Metrics | Overall trends and health | Counts, durations, endpoints, grant types, client labels, outcomes |
| Application logs | Technical error diagnosis | Correlation ID, standardized error code, exception class, dependency status |
| Audit events | Tracing security actions | Authenticated client, grant/revoke/consent action, timestamp, outcome, and appropriate actor |

Never record tokens or secrets in any of these sources. For logs, use correlation IDs to link requests across services. For audit events, restrict read permissions and set retention per policy. For metrics, keep only low-cardinality tags so they can be stored and queried long-term.

## 11. Implementation Checklist

- Actuator and Micrometer registry are configured according to the application's Spring Boot version.
- OAuth/OIDC endpoints are mapped to static labels and can be updated when endpoint URIs change.
- Grant types accept only allowlisted values; unknown values are grouped under **other**.
- Client IDs are mapped to stable operational labels; unauthenticated requests use **unresolved**.
- Outcomes distinguish success, redirect, client error, server error, and exception.
- Timers record both request counts and durations; histograms are enabled for meters requiring percentiles.
- Cardinality is bounded by design with an additional MeterFilter safeguard.
- Metrics endpoints are accessible only to Prometheus or internal monitoring systems.
- Dashboards support filtering by endpoint, grant type, client, and outcome.
- Alerts distinguish client protocol errors from server availability errors.
- Unit/integration tests verify tags, outcomes, endpoint allowlists, and zero sensitive data leakage.

When metrics are standardized across these four dimensions, operations teams can quickly pinpoint which endpoint or grant type is having issues, isolate affected clients, and monitor the impact of configuration changes. Combining aggregated metrics with controlled logs and audit events provides deep enough observability for a production Authorization Server.
